"""Просьбы окна к рабочему столу на маке — двойники `open_in_system` и `_show_in_folder`.

Обе дороги идут через `open`: без ключа она открывает названное тем, чем
система его открывает, с `-R` — показывает файл выделенным в Finder, не
запуская. Код возврата у `open` честный, поэтому исход читается по нему.
"""

from __future__ import annotations

import logging
import subprocess

logger = logging.getLogger(__name__)


def open_in_system(target: str) -> bool:
    """Отдать путь или ссылку тому, чем система их открывает, и сказать, дошло ли."""
    return _opened(["open", target], target)


def show_in_folder(target) -> bool:
    """Показать файл выделенным в Finder, не запуская его самого."""
    return _opened(["open", "-R", str(target)], target)


def _opened(args: list[str], target) -> bool:
    try:
        subprocess.run(args, check=True)
    except (OSError, subprocess.CalledProcessError):
        logger.exception("система не открыла: %s", target)
        return False
    return True
