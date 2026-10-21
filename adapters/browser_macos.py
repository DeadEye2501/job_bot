"""Поиск установленного браузера на маке — двойник `browser.find_browser`.

Ход «первый существующий файл по папкам программ» повторяет Windows-поиск:
общий вынести нельзя, не переписав Windows-код.
"""

from pathlib import Path

from adapters.browser import BRAVE, CHROME, EDGE, OPERA, VIVALDI, YANDEX, InstalledBrowser

_SYSTEM_APPS = Path("/Applications")

_INSIDE = (
    (CHROME, "Google Chrome.app/Contents/MacOS/Google Chrome", "chrome"),
    (OPERA, "Opera.app/Contents/MacOS/Opera", None),
    (BRAVE, "Brave Browser.app/Contents/MacOS/Brave Browser", None),
    (VIVALDI, "Vivaldi.app/Contents/MacOS/Vivaldi", None),
    (YANDEX, "Yandex.app/Contents/MacOS/Yandex", None),
    (EDGE, "Microsoft Edge.app/Contents/MacOS/Microsoft Edge", "msedge"),
)
"""Браузер, путь к исполняемому внутри папки программ, канал Playwright."""


def find_browser() -> InstalledBrowser | None:
    """Первый найденный: Chrome, Opera, Brave, Vivaldi, Яндекс.Браузер, Edge.

    Канал ставится только находке в `/Applications`: каналы `chrome` и
    `msedge` Playwright ищет там. Установленному в `~/Applications` канал не
    дан, и Playwright запускает его по пути.
    """
    for name, inside, channel in _INSIDE:
        for base in (_SYSTEM_APPS, Path.home() / "Applications"):
            path = base / inside
            if path.is_file():
                return InstalledBrowser(name, channel if base == _SYSTEM_APPS else None, path)
    return None
