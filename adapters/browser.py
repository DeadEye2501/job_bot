"""Браузер человека на движке Chromium под управлением Playwright."""

import logging
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from backend.domain.hosts import host_owns
from config import get_data_dir

logger = logging.getLogger(__name__)

BROWSER_DIR = get_data_dir() / "browser"

_PROGRAMS = ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")

# Перечень один на поиск и на подсказку человеку: разойдись они — подсказка врала бы.
BROWSER_NAMES = CHROME, OPERA, BRAVE, VIVALDI, YANDEX, EDGE = (
    "Chrome", "Opera", "Brave", "Vivaldi", "Яндекс.Браузер", "Edge",
)


@dataclass(frozen=True)
class InstalledBrowser:
    name: str
    channel: str | None
    executable: Path | None


def find_browser() -> InstalledBrowser | None:
    """Первый найденный: Chrome, Opera, Brave, Vivaldi, Яндекс.Браузер, Edge.

    Chrome и Edge Playwright водит по имени канала, остальных — по пути к
    исполняемому файлу.
    """
    for found in (
        _channel(CHROME, "chrome", "Google/Chrome/Application/chrome.exe"),
        _opera(),
        _by_path(BRAVE, "BraveSoftware/Brave-Browser/Application/brave.exe"),
        _by_path(VIVALDI, "Vivaldi/Application/vivaldi.exe"),
        _by_path(YANDEX, "Yandex/YandexBrowser/Application/browser.exe"),
        _channel(EDGE, "msedge", "Microsoft/Edge/Application/msedge.exe"),
    ):
        if found is not None:
            return found
    return None


def _candidates(relative: str) -> list[Path]:
    return [Path(os.environ[root]) / relative for root in _PROGRAMS if os.environ.get(root)]


def _first(relative: str) -> Path | None:
    return next((path for path in _candidates(relative) if path.is_file()), None)


def _channel(name: str, channel: str, relative: str) -> InstalledBrowser | None:
    return InstalledBrowser(name, channel, None) if _first(relative) else None


def _by_path(name: str, relative: str) -> InstalledBrowser | None:
    found = _first(relative)
    return InstalledBrowser(name, None, found) if found else None


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

    def __init__(self, browser: InstalledBrowser, always_visible: bool) -> None:
        self._browser = browser
        self._always_visible = always_visible
        self._playwright = None
        self._context = None
        self._profile_id: int | None = None
        self._sending = True
        self._as_person = False
        self._last_url = "about:blank"

    async def open_profile(
        self, profile_id: int, sending: bool = True, as_person: bool = False
    ) -> None:
        """Открыть профиль. `sending=False` — отклик под симуляцией: всё, что сайт
        отправил бы, обрывается в самом браузере (`hold_sending`), что бы ни нажали.

        `as_person` — в окне работает человек, а не агент (вход на сайт): браузер
        открыт без пометки «управляется программой». С ней вход Google отказывает
        («браузер небезопасен»), а человеку, входящему руками, она не нужна.
        """
        if (self._profile_id == profile_id and self._sending == sending
                and self._as_person == as_person and self._context is not None):
            return
        await self._close_context()
        if self._profile_id != profile_id:
            self._last_url = "about:blank"
        self._profile_id = profile_id
        self._sending = sending
        self._as_person = as_person
        await self._launch()

    async def page(self):
        """Последняя вкладка. Окно закрыл человек — профиль переоткрывается там же."""
        if self._context is None or not self._context.pages:
            await self._close_context()
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

    async def wait_closed(self, limit_sec: float) -> bool:
        """Ждать, пока человек закроет окно. Ждётся вкладка, а не весь браузер:
        иные браузеры после закрытия окна живут в фоне."""
        from playwright.async_api import TimeoutError as PlaywrightTimeout

        try:
            await (await self.page()).wait_for_event("close", timeout=limit_sec * 1000)
        except PlaywrightTimeout:
            return False
        await self._close_context()
        return True

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
            channel=self._browser.channel,
            executable_path=str(self._browser.executable) if self._browser.executable else None,
            # Запросы сервис-воркера идут мимо перехвата: при удержании их нет вовсе.
            service_workers="allow" if self._sending else "block",
            **(_PERSON_LAUNCH if self._as_person else {}),
        )
        if not self._sending:
            await self._context.route("**/*", hold_sending)
        if self._as_person:
            await self._context.add_init_script(_HIDE_WEBDRIVER)
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
        try:
            await page.goto(back_to)
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
        """Забыть закрытый контекст — если это нынешний, а не запоздалое событие прежнего."""
        if closed is self._context:
            self._context = None

    async def _close_context(self) -> None:
        if self._context is not None:
            context, self._context = self._context, None
            await context.close()


_SENDING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_CAPTCHA_HOSTS = ("recaptcha.net", "hcaptcha.com", "challenges.cloudflare.com",
                  "smartcaptcha.yandexcloud.net")
# У Google капча — только путь: на его же хостах живут Google Forms, а это форма отклика.
_GOOGLE_CAPTCHA_PATH = "/recaptcha/"
# Cloudflare проверяет человека и на хосте самого сайта, своим служебным путём.
_CLOUDFLARE_CHECK_PATH = "/cdn-cgi/challenge-platform/"


# Запуск без пометки «управляется программой»: без флага `--enable-automation`,
# который Playwright ставит сам. Песочница включена: без неё Playwright ставит
# `--no-sandbox`, а на флаги, которых Chrome не поддерживает, он вешает над
# страницей плашку.
_PERSON_LAUNCH = {
    "ignore_default_args": ["--enable-automation"],
    "chromium_sandbox": True,
}

# `navigator.webdriver` выставляет само подключение Playwright, и по нему вход
# Google отказывает («браузер небезопасен»). Прячется скриптом страницы, а не
# флагом `--disable-blink-features`: на тот Chrome тоже вешает плашку.
_HIDE_WEBDRIVER = "Object.defineProperty(Navigator.prototype, 'webdriver', {get: () => false})"


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
