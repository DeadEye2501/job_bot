"""Выбор платформенного модуля без загрузки API чужой ОС."""

import importlib
import sys
from types import ModuleType

_PACKAGE = "windows" if sys.platform == "win32" else "unsupported"


def implementation(subject: str) -> ModuleType:
    """Реализация предмета; macOS/Linux подключаются на следующих этапах."""
    name = f"{_PACKAGE}.{subject}" if _PACKAGE == "windows" else _PACKAGE
    return importlib.import_module(f"{__name__}.{name}")
