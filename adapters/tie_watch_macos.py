"""Сторож привязанных процессов на маке: гасит их, когда приложение кончилось.

Задания Windows «снять всё при закрытии» у мака нет. Его место держит
отдельный процесс: приложение пишет ему в трубу номера привязанных, а конец
трубы наступает, как бы приложение ни кончилось, — и обычным выходом, и
`kill -9`: трубу закрывает система.

Гаснет дерево, а не только привязанные: задание Windows наследуют и потомки,
а браузер агента — потомок драйвера. Процесс узнаётся по паре «номер + время
старта»: номер вышедшего процесса система раздаёт заново, и без времени
сторож погасил бы чужую программу человека.

Журнала сторож не пишет вовсе, и свою беду тоже: он ввозит `main.py` с его
журналом и крючком падений, а файл журнала, открытый вторым процессом, рвётся
на первой же ротации.
"""

import contextlib
import logging
import os
import signal
import sys
from collections.abc import Iterable
from pathlib import Path

from adapters.process_table_macos import process_table

TIE_WATCH_FLAG = "--tie-watch"
_STARTED = "lstart"


def self_command() -> list[str]:
    """Как запустить сторожа: та же программа с флагом сторожа."""
    if getattr(sys, "frozen", False):
        return [sys.executable, TIE_WATCH_FLAG]
    return [sys.executable, str(Path(__file__).resolve().parent.parent / "main.py"), TIE_WATCH_FLAG]


def watch(lines: Iterable[str]) -> None:
    """Запоминать привязанных, пока поток не кончится; потом погасить их деревья."""
    logging.disable(logging.CRITICAL)
    tied = {}
    for line in lines:
        pid = int(line)
        started = _started_of(process_table(_STARTED))
        if pid in started:
            tied[pid] = started[pid]
    for pid in _doomed(tied, process_table(_STARTED)):
        # Вышедший сам — уже то, чего сторож добивается.
        with contextlib.suppress(ProcessLookupError):
            os.kill(pid, signal.SIGKILL)


def _started_of(table: list[tuple[int, int, str]]) -> dict[int, str]:
    return {pid: started for pid, _parent, started in table}


def _doomed(tied: dict[int, str], table: list[tuple[int, int, str]]) -> list[int]:
    """Привязанные, всё ещё те же самые, и все их потомки."""
    started = _started_of(table)
    children: dict[int, list[int]] = {}
    for pid, parent, _started in table:
        children.setdefault(parent, []).append(pid)
    doomed = [pid for pid, then in tied.items() if started.get(pid) == then]
    for pid in doomed:
        doomed.extend(child for child in children.get(pid, []) if child not in doomed)
    return doomed
