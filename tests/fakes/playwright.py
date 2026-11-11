"""Браузер под `BrowserHost`: процесс профиля, подключение к нему и события его контекста, без браузера."""

import asyncio
from pathlib import Path

from playwright.async_api import Error as PlaywrightError

from adapters.browser import BrowserHost
from tests.fakes.browser import CHROME


class BrowserProcess:
    """Процесс браузера: живёт, пока не выйдет сам или его не погасят."""

    def __init__(self):
        self.pid = 4242
        self.returncode = None
        self.terminated = False
        self._done = asyncio.Event()

    async def wait(self) -> int:
        await self._done.wait()
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True
        self.exit()

    def exit(self) -> None:
        self.returncode = 0
        self._done.set()


class DrivenContext:
    """Запущенный профиль: где он, что перехвачено, кто слушает его события."""

    def __init__(self, path):
        self.path = path
        self.routes = []
        self.init_scripts = []
        self.handlers = {}
        self.closed = False
        self.pages = [_DrivenPage()]

    async def route(self, pattern, handler):
        self.routes.append((pattern, handler))

    async def add_init_script(self, script):
        self.init_scripts.append(script)

    def on(self, event, handler):
        self.handlers.setdefault(event, []).append(handler)

    def fire(self, event):
        """Послать событие контекста его слушателям, как это делает Playwright."""
        for handler in self.handlers.get(event, []):
            handler(self)


class _DrivenPage:
    url = "about:blank"

    def on(self, *_event):
        return None

    async def goto(self, url, **_options):
        self.url = url


class _Session:
    def __init__(self, browser):
        self._browser = browser

    async def send(self, method, _params=None):
        if method == "Browser.close":
            self._browser.quit()
            if self._browser.leaves_silently:
                await asyncio.Event().wait()


class _DrivenBrowser:
    """Браузер, к которому подключился Playwright: выходит по `Browser.close`.

    `leaves_silently` — выходит, не ответив: так ведёт себя браузер, окно
    которого уже закрыл человек.
    """

    def __init__(self, process, context, leaves_silently):
        self.process, self.contexts = process, [context]
        self.leaves_silently = leaves_silently
        self._connected = True

    def is_connected(self):
        return self._connected

    async def new_browser_cdp_session(self):
        if not self._connected:
            raise PlaywrightError("Target page, context or browser has been closed")
        return _Session(self)

    def quit(self):
        self._connected = False
        self.process.exit()
        self.contexts[0].closed = True
        self.contexts[0].fire("close")

    async def close(self):
        self._connected = False


class _Playwright:
    """Playwright и запуски браузера: `started` — все запуски, `driven` — процессы
    и `contexts` — профили агента.

    Запуск без порта — браузер человека: его процесс отдаёт `person`.
    Подключение ждёт `connecting`, если оно задано, и бросает `refusal`.
    """

    def __init__(self):
        self.started = []
        self.driven = []
        self.contexts = []
        self.person = None
        self.connecting = None
        self.refusal = None
        self.leaves_silently = False
        self.chromium = self
        self._waiting = {}

    async def start(self):
        return self

    async def stop(self):
        return None

    async def spawn(self, *argv, **_options):
        self.started.append(argv)
        if not any(arg.startswith("--remote-debugging-port") for arg in argv):
            return self.person()
        profile = Path(next(a for a in argv if a.startswith("--user-data-dir=")).split("=", 1)[1])
        profile.mkdir(parents=True, exist_ok=True)
        port = str(9000 + len(self.started))
        (profile / "DevToolsActivePort").write_text(f"{port}\n/devtools/browser/x")
        process = BrowserProcess()
        self.driven.append(process)
        self._waiting[port] = (process, profile)
        return process

    async def connect_over_cdp(self, endpoint):
        process, profile = self._waiting.pop(endpoint.rsplit(":", 1)[1])
        if self.connecting is not None:
            await self.connecting.wait()
        if self.refusal is not None:
            raise self.refusal
        self.contexts.append(DrivenContext(str(profile)))
        return _DrivenBrowser(process, self.contexts[-1], self.leaves_silently)


def driven_host(monkeypatch, on_closed=lambda: None) -> tuple[BrowserHost, _Playwright]:
    """Хозяин браузера на подделке Playwright; второе — она, с запусками и профилями."""
    playwright = _Playwright()
    monkeypatch.setattr("playwright.async_api.async_playwright", lambda: playwright)
    monkeypatch.setattr("adapters.app_tied_process.tie_children_named", lambda _name: None)
    monkeypatch.setattr("adapters.browser.asyncio.create_subprocess_exec", playwright.spawn)
    monkeypatch.setattr("adapters.browser.tie_to_app", lambda _pid: None)
    return BrowserHost(CHROME, always_visible=True, on_closed=on_closed), playwright
