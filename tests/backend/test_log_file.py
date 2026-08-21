"""Следствия файла журнала: поворот по размеру и недоступный файл.

Поворот идёт переименованием, и файл на его месте бывает занят — чужой
программой или второй копией. Обработчик, замолчавший на этом, унёс бы с собой
весь журнал, а человек узнал бы об этом, только открыв пустой файл.

Соседи по слою — свои: кольцо записей смотрит `test_log_buffer.py`,
вымарывание секретов — `test_log_secrets.py`.
"""

import os

from backend.log_file import LogFileHandler
from tests.backend.fixtures.logs import record


def _busy(source, dest):
    """Отказ ОС переименовать файл, открытый другим процессом."""
    raise PermissionError(32, "файл занят другим процессом")


def test_a_rotation_into_a_busy_file_does_not_silence_the_handler(
    clean_log_file, monkeypatch
):
    """Ротация, упёршаяся в занятый файл, обработчика не выключает.

    Переименовать открытый файл Windows не даёт, а открыт он бывает у
    второй копии приложения — базу они делят и сегодня. Штатный переход
    оставляет поток закрытым, и каждая следующая запись упирается в ту же
    ротацию: журнал замолкает до перезапуска, то есть теряется ровно та
    история, ради которой он заведён.
    """
    handler = LogFileHandler(
        clean_log_file, encoding="utf-8", maxBytes=1, backupCount=1
    )
    monkeypatch.setattr(os, "rename", _busy)

    handler.emit(record("до поворота"))
    handler.emit(record("после поворота"))
    handler.close()

    lines = clean_log_file.read_text(encoding="utf-8").splitlines()
    assert "после поворота" in lines
    assert any("не повернуть" in line for line in lines)
