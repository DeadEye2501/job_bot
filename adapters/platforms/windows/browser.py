"""Поиск браузеров и видимых окон Windows."""

import ctypes
import os
from ctypes import wintypes
from pathlib import Path

from adapters.platforms.browser_types import (
    BRAVE, CHROME, EDGE, OPERA, VIVALDI, YANDEX, InstalledBrowser,
)

_PROGRAMS = ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")


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


def has_window(pid: int) -> bool:
    """Есть ли у процесса видимое окно верхнего уровня."""
    enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32 = ctypes.WinDLL("user32")
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    found = False

    def look(window, _param) -> bool:
        nonlocal found
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(window, ctypes.byref(owner))
        found = owner.value == pid and bool(user32.IsWindowVisible(window))
        return not found

    user32.EnumWindows(enum_proc(look), 0)
    return found
