"""Пути и безопасная уборка файла Windows-обновления."""

import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def new_exe_path() -> Path:
    """Куда ложится скачанное: рядом с exe, под его именем с `.new`. Рядом, а не
    во временной папке: подмена — переименование, а оно не ходит между дисками."""
    exe = Path(sys.executable)
    return exe.with_name(exe.name + ".new")


def remove_leftover(path: Path) -> None:
    """Убрать файл обновления — недокачанный или отслуживший. Занятый — свежий файл
    держит антивирус, копия-подменщик ещё не вышла — остаётся до следующего
    запуска, который его уберёт; зовущий от этого не падает."""
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.warning("не удалось убрать файл обновления %s", path, exc_info=True)
