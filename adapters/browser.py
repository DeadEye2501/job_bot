"""Браузер на профилях агрегаторов: агент водит его через Playwright, человек
входит в нём обычным процессом."""

import asyncio
import contextlib
import logging
import os
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from adapters.app_tied_process import tie_to_app
from adapters.process_windows import has_window
from backend.domain.hosts import host_owns
from config import get_data_dir

logger = logging.getLogger(__name__)

BROWSER_DIR = get_data_dir() / "browser"

# Как часто смотреть, открыто ли ещё окно входа: человеку закрытие видно сразу,
# и полсекунды задержки он не заметит.
_WINDOW_POLL_SEC = 0.5

# Сколько ждать, пока закрытый окном браузер выйдет сам. Браузер на Chromium
# копит куки до тридцати секунд, прежде чем записать их на диск; на выходе он
# пишет их сразу, а оставшийся в фоне за это время успеет записать сам.
_OWN_EXIT_SEC = 30


class BrowserClosed(RuntimeError):
    """Окно браузера агента закрыл человек: работа остановлена, и открывать его
    снова нельзя до следующей работы."""

_PROGRAMS = ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")

# Перечень один на поиск и на подсказку человеку: разойдись они — подсказка врала бы.
BROWSER_NAMES = CHROME, OPERA, BRAVE, VIVALDI, YANDEX, EDGE = (
    "Chrome", "Opera", "Brave", "Vivaldi", "Яндекс.Браузер", "Edge",
)


@dataclass(frozen=True)
class InstalledBrowser:
    name: str
    channel: str | None
    executable: Path


def find_browser() -> InstalledBrowser | None:
    """Первый найденный: Chrome, Opera, Brave, Vivaldi, Яндекс.Браузер, Edge.

    Chrome и Edge Playwright водит по имени канала, остальных — по пути к
    исполняемому файлу. Путь известен у всех: человеку для входа браузер
    запускается им самим, без Playwright (`BrowserHost.let_person_in`).
    """
    for found in (
        _installed(CHROME, "Google/Chrome/Application/chrome.exe", "chrome"),
        _opera(),
        _installed(BRAVE, "BraveSoftware/Brave-Browser/Application/brave.exe"),
        _installed(VIVALDI, "Vivaldi/Application/vivaldi.exe"),
        _installed(YANDEX, "Yandex/YandexBrowser/Application/browser.exe"),
        _installed(EDGE, "Microsoft/Edge/Application/msedge.exe", "msedge"),
    ):
        if found is not None:
            return found
    return None


def _candidates(relative: str) -> list[Path]:
    return [Path(os.environ[root]) / relative for root in _PROGRAMS if os.environ.get(root)]


def _first(relative: str) -> Path | None:
    return next((path for path in _candidates(relative) if path.is_file()), None)


def _installed(name: str, relative: str, channel: str | None = None) -> InstalledBrowser | None:
    found = _first(relative)
    return InstalledBrowser(name, channel, found) if found else None


def _opera() -> InstalledBrowser | None:
    """Opera: настоящий opera.exe лежит в папке версии, а верхний — запускающая обёртка."""
    for home in _candidates("Programs/Opera"):
        versions = sorted(
            (d for d in home.glob("*") if d.is_dir() and (d / "opera.exe").is_file()),
            key=lambda d: [int(p) for p in d.name.split(".") if p.isdigit()],
        )
        if versions:
            return InstalledBrowser(OPERA, None, versions[-1] / "opera.exe")
    return None


def remove_profile(profile_id: int) -> None:
    """Снести профиль браузера агрегатора — при удалении агрегатора."""
    try:
        shutil.rmtree(BROWSER_DIR / str(profile_id))
    except FileNotFoundError:
        return
    except OSError:
        logger.exception("профиль браузера %d не удалён", profile_id)


class BrowserHost:
    """Один браузер приложения: профиль за профилем, развёрнутый или свёрнутый."""

    def __init__(self, browser: InstalledBrowser, always_visible: bool, on_closed: Callable[[], None]) -> None:
        """`on_closed` — человек закрыл окно браузера агента: он остановил работу,
        и открывать окно снова нельзя — закрытое раз за разом возвращалось бы."""
        self._browser = browser
        self._always_visible = always_visible
        self._on_closed = on_closed
        self._playwright = None
        self._context = None
        self._profile_id: int | None = None
        self._sending = True
        self._last_url = "about:blank"
        self._stopped = False

    async def open_profile(self, profile_id: int, sending: bool = True) -> None:
        """Открыть профиль. `sending=False` — отклик под симуляцией: всё, что сайт
        отправил бы, обрывается в самом браузере (`hold_sending`), что бы ни нажали.
        """
        self._stopped = False
        if self._profile_id == profile_id and self._sending == sending and self._context is not None:
            return
        await self._close_context()
        if self._profile_id != profile_id:
            self._last_url = "about:blank"
        self._profile_id = profile_id
        self._sending = sending
        await self._launch()

    async def let_person_in(self, profile_id: int, url: str, limit_sec: float) -> bool:
        """Открыть человеку профиль на этом адресе обычным браузером и ждать, пока
        он закроет окно; ответ — закрыл ли за срок.

        Обычным процессом, а не через Playwright: вход Google отказывает браузеру,
        которым управляет программа («браузер или приложение небезопасны»), и
        узнаёт его не по одному признаку, который можно спрятать. Ведомый браузер
        на профиле закрывается до запуска — профиль держит один браузер, — и
        следующий зов агента открывает профиль там, где человек начинал.

        Чем бы ни кончилось — закрытым окном, сроком, «Стопом», — процесс гасится:
        иные браузеры после закрытия окна живут в фоне и держали бы профиль, а
        брошенное окно приняло бы следующий вход себе, и тот кончился бы сразу.
        Закрытому окном сперва дают выйти самому (`_OWN_EXIT_SEC`): окно пропадает
        раньше, чем браузер допишет профиль, и погашенный в этот миг он унёс бы
        куки входа с собой.
        """
        await self._close_context()
        self._profile_id, self._sending, self._last_url = profile_id, True, url
        self._stopped = False
        process = await asyncio.create_subprocess_exec(
            str(self._browser.executable), f"--user-data-dir={BROWSER_DIR / str(profile_id)}",
            "--no-first-run", "--no-default-browser-check", url,
        )
        tie_to_app(process.pid)
        try:
            closed = await _window_closed(process, limit_sec)
            if closed:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(process.wait(), _OWN_EXIT_SEC)
            return closed
        finally:
            if process.returncode is None:
                process.terminate()
                await process.wait()

    async def page(self):
        """Последняя вкладка; профиль, ещё не открытый, открывается там, где был.

        Браузер без вкладок, которого приложение не закрывало, закрыл человек:
        Playwright сообщает о закрытии браузера позже, чем убирает вкладки, а
        оставшийся в фоне не сообщает вовсе. Закрытое человеком не поднимается
        до следующей работы (`BrowserClosed`).
        """
        if self._context is not None and not self._context.pages:
            await self._close_context()
            self._closed_by_person()
        if self._stopped:
            raise BrowserClosed
        if self._context is None:
            await self._launch()
        current = self._context.pages[-1]
        self._last_url = current.url
        return current

    async def show(self) -> None:
        await self._place(on_screen=True)

    async def hide_back(self) -> None:
        if not self._always_visible:
            await self._place(on_screen=False)

    async def clear_cache(self) -> None:
        page = await self.page()
        cdp = await self._context.new_cdp_session(page)
        await cdp.send("Network.clearBrowserCache")

    async def close(self) -> None:
        try:
            await self._close_context()
        finally:
            if self._playwright is not None:
                playwright, self._playwright = self._playwright, None
                await playwright.stop()

    async def _launch(self) -> None:
        from playwright.async_api import Error as PlaywrightError
        from playwright.async_api import async_playwright

        from adapters.app_tied_process import tie_children_named

        if self._playwright is None:
            self._playwright = await async_playwright().start()
            tie_children_named("node.exe")
        self._context = await self._playwright.chromium.launch_persistent_context(
            str(BROWSER_DIR / str(self._profile_id)),
            headless=False,
            **context_options(self._browser, sending=self._sending),
        )
        if not self._sending:
            await self._context.route("**/*", hold_sending)
        self._context.on("close", self._forget_context)
        self._context.on("page", _accept_dialogs)
        for opened in self._context.pages:
            _accept_dialogs(opened)
        page = self._context.pages[-1] if self._context.pages else await self._context.new_page()
        # Адрес запоминается до сворачивания: `_place` спрашивает `page()`, а та
        # перезаписала бы его адресом пустой вкладки, и форма потерялась бы.
        back_to = self._last_url
        if not self._always_visible:
            await self._place(on_screen=False)
        if back_to == "about:blank":
            return
        # Ждать разметки, а не полной загрузки: тяжёлые страницы агрегаторов
        # дотягивают своё полминуты, а работать агенту можно уже с разметкой.
        try:
            await page.goto(back_to, wait_until="domcontentloaded")
        except PlaywrightError:
            logger.exception("прежняя страница профиля %d не открылась", self._profile_id)

    async def _place(self, on_screen: bool) -> None:
        """Развернуть или свернуть окно — через CDP, без перезапуска: форма не теряется."""
        page = await self.page()
        cdp = await self._context.new_cdp_session(page)
        window = await cdp.send("Browser.getWindowForTarget")
        state = "normal" if on_screen else "minimized"
        await cdp.send("Browser.setWindowBounds",
                       {"windowId": window["windowId"], "bounds": {"windowState": state}})
        if on_screen:
            await page.bring_to_front()

    def _forget_context(self, closed) -> None:
        """Закрылся нынешний контекст — его закрыл человек: своё приложение забывает
        контекст до закрытия (`_close_context`), и запоздалое событие прежнего
        сюда не доходит. Человек этим остановил работу (`on_closed`)."""
        if closed is self._context:
            self._context = None
            self._closed_by_person()

    def _closed_by_person(self) -> None:
        """Человек закрыл окно: работа остановлена — один раз, сколько бы
        признаков закрытия ни пришло."""
        if not self._stopped:
            self._stopped = True
            self._on_closed()

    async def _close_context(self) -> None:
        if self._context is not None:
            context, self._context = self._context, None
            await context.close()


async def _window_closed(process, limit_sec: float) -> bool:
    """Закрыл ли человек окно браузера за срок.

    Ждётся окно, а не процесс: иные браузеры после закрытия окна живут в фоне.
    Пока окно не показалось, закрытым оно не считается — браузер поднимается не
    сразу; вышедший без окна процесс ждать нечего.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + limit_sec
    shown = False
    while loop.time() < deadline:
        if has_window(process.pid):
            shown = True
        elif shown or process.returncode is not None:
            return True
        await asyncio.sleep(_WINDOW_POLL_SEC)
    return False


_SENDING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_CAPTCHA_HOSTS = ("recaptcha.net", "hcaptcha.com", "challenges.cloudflare.com",
                  "smartcaptcha.yandexcloud.net")
# У Google капча — только путь: на его же хостах живут Google Forms, а это форма отклика.
_GOOGLE_CAPTCHA_PATH = "/recaptcha/"
# Cloudflare проверяет человека и на хосте самого сайта, своим служебным путём.
_CLOUDFLARE_CHECK_PATH = "/cdn-cgi/challenge-platform/"


def context_options(browser: InstalledBrowser, *, sending: bool) -> dict:
    """С чем запускается браузер агента.

    Загрузки запрещены всегда, и запрещены самим браузером, а не словами агенту:
    файл с чужого сайта на диске человека — риск, который наставление не
    закрывает, а скачивать агенту нечего — свои файлы он прикладывает сам.
    Запросы сервис-воркера идут мимо перехвата: при удержании их нет вовсе.
    """
    return {
        "channel": browser.channel,
        # Канал Playwright находит сам; путь ему нужен только без канала.
        "executable_path": None if browser.channel else str(browser.executable),
        "service_workers": "allow" if sending else "block",
        "accept_downloads": False,
    }


async def hold_sending(route) -> None:
    """Оборвать запрос, несущий данные на сервер, — кроме ответа капче.

    Последнюю кнопку формы код не знает, а подпись у неё бывает любой; отправка
    же данных — всегда такой запрос. Капча — проверка человека, а не отклик:
    без неё форму не пройти и под симуляцией.
    """
    request = route.request
    if request.method in _SENDING_METHODS and not _is_captcha(request.url):
        logger.info("симуляция: %s %s не отправлен", request.method, request.url)
        await route.abort("blockedbyclient")
        return
    await route.continue_()


def _is_captcha(url: str) -> bool:
    parts = urlsplit(url)
    host = parts.hostname or ""
    if parts.path.startswith(_CLOUDFLARE_CHECK_PATH):
        return True
    if host in ("google.com", "www.google.com"):
        return parts.path.startswith(_GOOGLE_CAPTCHA_PATH)
    return any(host_owns(h, host) for h in _CAPTCHA_HOSTS)


def _accept_dialogs(page) -> None:
    """Подтверждать диалоги вкладки: `confirm()` Playwright по умолчанию отклоняет,
    и форма работодателя с подтверждением отправки срывалась бы."""
    page.on("dialog", lambda dialog: dialog.accept())
