"""Файлы-пустышки в тестах: «установленная программа» — это просто файл на своём месте."""

from pathlib import Path


def empty_file(root: Path, relative: str) -> Path:
    """Завести пустой файл `root / relative` вместе с папками; ответ — его путь."""
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")
    return path
