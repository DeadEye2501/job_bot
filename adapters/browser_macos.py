"""Поиск установленного браузера на маке — двойник `browser.find_browser`.

Ход «первый существующий файл по папкам программ» повторяет Windows-поиск:
общий вынести нельзя, не переписав Windows-код.
"""

from pathlib import Path

from adapters.browser import BRAVE, CHROME, EDGE, OPERA, VIVALDI, YANDEX, InstalledBrowser

_SYSTEM_APPS = Path("/Applications")

_INSIDE = (
    (CHROME, "Google Chrome.app/Contents/MacOS/Google Chrome"),
    (OPERA, "Opera.app/Contents/MacOS/Opera"),
    (BRAVE, "Brave Browser.app/Contents/MacOS/Brave Browser"),
    (VIVALDI, "Vivaldi.app/Contents/MacOS/Vivaldi"),
    (YANDEX, "Yandex.app/Contents/MacOS/Yandex"),
    (EDGE, "Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
)
"""Браузер и путь к исполняемому внутри папки программ."""


def find_browser() -> InstalledBrowser | None:
    """Первый найденный: Chrome, Opera, Brave, Vivaldi, Яндекс.Браузер, Edge."""
    for name, inside in _INSIDE:
        for base in (_SYSTEM_APPS, Path.home() / "Applications"):
            path = base / inside
            if path.is_file():
                return InstalledBrowser(name, path)
    return None
