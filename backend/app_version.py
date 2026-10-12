"""Версия приложения: единственное место, где оно знает свой номер.

Тег релиза на GitHub повторяет этот номер с приставкой `v`, а не наоборот.
"""

VERSION = "1.0.1"


def _parse(text: str) -> tuple[int, int, int] | None:
    """Номер из тега вида `v1.2.3` или `1.2.3`; не номер — пусто."""
    parts = text.removeprefix("v").split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        return None
    return int(parts[0]), int(parts[1]), int(parts[2])


def newer_version(tag: str) -> str | None:
    """Номер из тега для показа, если релиз новее запущенного; иначе пусто.

    Сравнение числами, а не строкой: `1.10.0` новее `1.9.0`.
    """
    found = _parse(tag)
    if found is None or found <= _parse(VERSION):
        return None
    return ".".join(map(str, found))
