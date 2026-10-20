"""Описание установленного браузера, общее для реализаций ОС."""

from dataclasses import dataclass
from pathlib import Path

# Перечень один на поиск и на подсказку человеку: разойдись они — подсказка врала бы.
BROWSER_NAMES = CHROME, OPERA, BRAVE, VIVALDI, YANDEX, EDGE = (
    "Chrome", "Opera", "Brave", "Vivaldi", "Яндекс.Браузер", "Edge",
)


@dataclass(frozen=True)
class InstalledBrowser:
    name: str
    channel: str | None
    executable: Path
