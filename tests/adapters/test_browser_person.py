"""Вход человека на сайт: обычный браузер на профиле агрегатора, а не ведомый.

Вход Google отказывает браузеру, которым управляет программа («браузер или
приложение небезопасны»), и узнаёт его не по одному признаку, который можно
спрятать. Поэтому человек входит в браузере, запущенном обычным процессом, а
агент открывает тот же профиль после него.
"""

import asyncio

import pytest

from adapters.browser import BROWSER_DIR
from tests.fakes.browser import CHROME
from tests.fakes.playwright import driven_host


class _Process:
    """Процесс браузера: живёт, пока его не погасят или не выйдет сам."""

    def __init__(self, exits_with_window: bool):
        self.pid = 4242
        self.exits_with_window = exits_with_window
        self.showed = False
        self.returncode = None
        self.terminated = False
        self._done = asyncio.Event()

    async def wait(self) -> int:
        await self._done.wait()
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True
        self._exit()

    def _exit(self) -> None:
        self.returncode = 0
        self._done.set()


def _host(monkeypatch, windows: list[bool], *, exits_with_window=True):
    """Хозяин браузера на подделках. `windows` — видно ли окно процесса на
    каждом взгляде; кончились — окна нет. Ответ — хозяин, запуски, Playwright, процесс."""
    (host, playwright), started = driven_host(monkeypatch), []
    process = _Process(exits_with_window)
    seen = iter(windows)

    async def spawn(*argv, **_options):
        started.append(argv)
        return process

    def has_window(pid):
        shown = next(seen, False)
        if shown:
            process.showed = True
        elif process.showed and process.exits_with_window:
            # Закрытый браузер выходит не в тот же миг: он ещё дописывает профиль.
            asyncio.get_running_loop().call_later(0.02, process._exit)
        return shown and pid == process.pid

    monkeypatch.setattr("adapters.browser.asyncio.create_subprocess_exec", spawn)
    monkeypatch.setattr("adapters.browser.has_window", has_window)
    monkeypatch.setattr("adapters.browser.tie_to_app", lambda _pid: None)
    monkeypatch.setattr("adapters.browser._WINDOW_POLL_SEC", 0)
    monkeypatch.setattr("adapters.browser._OWN_EXIT_SEC", 0.2)
    return host, started, playwright, process


async def test_a_person_logs_in_with_a_plain_browser_on_the_site_profile(monkeypatch):
    host, started, playwright, _ = _host(monkeypatch, [False, True, True])
    await host.open_profile(7)

    assert await host.let_person_in(7, "https://site.test/", 60) is True

    ((program, *args),) = started
    assert program == str(CHROME.executable)
    assert f"--user-data-dir={BROWSER_DIR / '7'}" in args and args[-1] == "https://site.test/"
    assert not any(arg.startswith("--remote-debugging") for arg in args)
    # Ведомый браузер на том же профиле закрыт до запуска: профиль держит один браузер.
    assert playwright.contexts[0].closed


async def test_a_closed_browser_is_let_to_finish_writing_the_login(monkeypatch):
    """Окно закрыто, а браузер ещё пишет на диск куки входа: погашенный в этот
    миг, он унёс бы вход с собой."""
    host, _, _, process = _host(monkeypatch, [True, True])

    assert await host.let_person_in(7, "https://site.test/", 60) is True
    assert process.returncode == 0 and not process.terminated


async def test_a_browser_living_on_after_its_window_closed_is_put_out(monkeypatch):
    """Иные браузеры после закрытия окна живут в фоне: ждётся окно, а не процесс,
    и оставшийся процесс гасится — иначе он держал бы профиль."""
    host, _, _, process = _host(monkeypatch, [True, True], exits_with_window=False)

    assert await host.let_person_in(7, "https://site.test/", 60) is True
    assert process.terminated


async def test_after_the_person_the_agent_opens_the_same_profile_on_the_site(monkeypatch):
    host, _, playwright, _ = _host(monkeypatch, [True])

    await host.let_person_in(7, "https://site.test/", 60)
    page = await host.page()

    assert playwright.contexts[-1].path == str(BROWSER_DIR / "7") and page.url == "https://site.test/"


async def test_a_window_left_open_past_the_limit_frees_the_profile(monkeypatch):
    host, _, _, process = _host(monkeypatch, [True] * 10_000)

    assert await host.let_person_in(7, "https://site.test/", 0.01) is False
    assert process.terminated


async def test_a_stopped_login_puts_the_browser_out(monkeypatch):
    """«Стоп» посреди входа не оставляет окна на профиле."""
    host, _, _, process = _host(monkeypatch, [True] * 10_000)
    login = asyncio.create_task(host.let_person_in(7, "https://site.test/", 60))
    await asyncio.sleep(0.01)

    login.cancel()
    with pytest.raises(asyncio.CancelledError):
        await login

    assert process.terminated
