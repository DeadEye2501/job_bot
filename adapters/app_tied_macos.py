"""Дочерние процессы, которые гасятся вместе с приложением, — двойник `app_tied_process`.

Привязанных держит сторож `tie_watch_macos`: первый же `tie_to_app` поднимает
его своим процессом, дальше номера идут ему в трубу.
"""

import logging
import os
import subprocess
from pathlib import Path

from adapters.process_table_macos import process_table
from adapters.tie_watch_macos import self_command

_log = logging.getLogger(__name__)

_watcher: subprocess.Popen | None = None


def tie_to_app(pid: int) -> None:
    """Привязать процесс к приложению: сторож погасит его, когда приложение кончится.

    Не вышло — запись в журнал, а процесс живёт как был: обычное закрытие окна
    снимет его и так, без привязки он переживёт лишь аварийный выход.
    """
    global _watcher
    try:
        if _watcher is None:
            _watcher = subprocess.Popen(
                self_command(), stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, start_new_session=True, text=True,
            )
        _watcher.stdin.write(f"{pid}\n")
        _watcher.stdin.flush()
    except OSError:
        _log.exception("процесс %s не привязан к приложению", pid)


def tie_children_named(name: str) -> int:
    """Привязать дочерние процессы приложения с этим именем. Ответ — сколько привязано.

    Имя приходит в виде Windows (`node.exe`); на маке у программ расширения
    нет, и оно отбрасывается.
    """
    image = name.removesuffix(".exe")
    count = 0
    for pid, command in _children():
        if Path(command).name == image:
            tie_to_app(pid)
            count += 1
    return count


def _children() -> list[tuple[int, str]]:
    """Дочерние процессы приложения: номер и путь к программе.

    Неудача `ps` — запись в журнал и пустой список: исход тот же, что у
    несостоявшейся привязки, работе он не мешает.
    """
    try:
        table = process_table("comm")
    except (OSError, subprocess.CalledProcessError):
        _log.exception("дочерние процессы приложения не перечислены")
        return []
    return [(pid, command) for pid, parent, command in table if parent == os.getpid()]
