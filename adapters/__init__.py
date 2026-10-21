"""Адаптеры к внешнему миру.

На маке два Windows-модуля подменяются двойниками под своими же именами:
`process_windows` и `app_tied_process` ввозят по имени в четырёх местах, и
выбор здесь оставляет те строки нетронутыми. Ставится и запись в
`sys.modules`, и атрибут пакета: `from adapters import app_tied_process` идёт
через атрибут. Двойник грузится строкой, чтобы сборщик Windows-exe его не видел.
"""

import importlib
import sys

if sys.platform == "darwin":
    for _windows_name, _mac_name in (
        ("process_windows", "process_macos"),
        ("app_tied_process", "app_tied_macos"),
    ):
        _twin = importlib.import_module(f"{__name__}.{_mac_name}")
        sys.modules[f"{__name__}.{_windows_name}"] = _twin
        globals()[_windows_name] = _twin
