"""Адаптеры к внешнему миру.

На маке два Windows-модуля подменяются двойниками под своими же именами:
`process_windows` и `app_tied_process` ввозят по имени, и выбор здесь
оставляет те строки ввоза нетронутыми. Ставится и запись в `sys.modules`, и
атрибут пакета: `from adapters import app_tied_process` идёт через атрибут.
Двойник грузится строкой, чтобы сборщик Windows-exe его не видел.
"""

import importlib
import sys

if sys.platform == "darwin":
    for _windows_name, _twin_path in (
        ("process_windows", "adapters.process_macos"),
        ("app_tied_process", "adapters.app_tied_macos"),
    ):
        _twin = importlib.import_module(_twin_path)
        sys.modules[f"{__name__}.{_windows_name}"] = _twin
        globals()[_windows_name] = _twin
