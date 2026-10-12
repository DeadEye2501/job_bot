"""Подмена exe скачанным обновлением — копией приложения в режиме `--update`.

Отличие от `backend/update_download`: тот качает внутри приложения, а здесь
работа отдельного процесса без окна, базы и замка единственной копии. Работающий
exe Windows подменить не даёт, поэтому подменяет его копия, дождавшись выхода.

Журнал приложения копия не трогает: файл его сторожит замок, а она замка не
берёт. Свои записи она ведёт в отдельный файл во временной папке.
"""

import ctypes
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from backend.update_download import new_exe_path, remove_leftover

logger = logging.getLogger(__name__)

UPDATE_FLAG = "--update"

_ATTEMPTS = 30
_PAUSE_SEC = 1.0
_WAIT_MS = 60_000
_SYNCHRONIZE = 0x00100000
# Оба запуска — копии из приложения и приложения из копии — отвязаны от
# запустившего: тот выходит сразу следом, и запущенный не должен уйти вместе
# с его группой процессов.
_DETACHED = 0x00000008 | 0x00000200


def updater_copy() -> Path:
    """Где лежит копия-подменщик: во временной папке, а не рядом с exe — рядом
    лежит тот файл, который она заменяет."""
    return Path(tempfile.gettempdir()) / "JobBot-update.exe"


def launch_updater(new: Path) -> None:
    """Скопировать себя во временную папку и запустить копию подменять exe.

    Ждать копии велено родителя, а не себя: собранный exe — загрузчик PyInstaller,
    а питон живёт его дочерним процессом; загрузчик держит `JobBot.exe` дольше и
    выходит последним, подчистив распаковку.
    """
    exe = Path(sys.executable)
    shutil.copy2(exe, updater_copy())
    _start([str(updater_copy()), UPDATE_FLAG, str(os.getppid()), str(exe), str(new)])


def run(args: list[str]) -> int:
    """Режим `--update`: дождаться выхода приложения, подменить exe, запустить его.

    Exe запускается при любом исходе — подменить не вышло, скачанное пропало в
    карантин, — потому что человек нажал «обновить» и ждёт приложения, а не
    пустого рабочего стола. Ответ — код выхода копии.
    """
    pid, exe, new = int(args[0]), Path(args[1]), Path(args[2])
    _log_to_own_file()
    replaced = False
    try:
        _wait_for_exit(pid)
        replaced = _replace(new, exe)
    # Беда копии остаётся в её журнале: дойди она до общего крючка падений, легла
    # бы в журнал приложения, которое к тому мигу, может, уже снова живо.
    except Exception:
        logger.exception("подмена сорвалась, запускается прежний exe: %s", exe)
    finally:
        _start([str(exe)])
    return 0 if replaced else 1


def clear_leftovers() -> None:
    """При обычном запуске убрать оставшееся от обновления: скачанный файл и
    копию-подменщик."""
    for leftover in (new_exe_path(), updater_copy()):
        remove_leftover(leftover)


def _start(args: list[str]) -> None:
    """Запустить собранный exe отвязанным и со свежей распаковкой: запущенный из
    собранного, он иначе может взять распаковку запустившего, а её сотрут, едва
    тот выйдет."""
    subprocess.Popen(args, creationflags=_DETACHED, close_fds=True,
                     env={**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"})


def _log_to_own_file() -> None:
    """Свой журнал, без передачи наверх, к обработчикам приложения."""
    logger.propagate = False
    logger.addHandler(logging.FileHandler(
        Path(tempfile.gettempdir()) / "JobBot-update.log", encoding="utf-8"))
    logger.setLevel(logging.INFO)


def _wait_for_exit(pid: int) -> None:
    """Дождаться выхода процесса; не открылся — его уже нет, ждать нечего."""
    kernel = ctypes.windll.kernel32
    kernel.OpenProcess.restype = ctypes.c_void_p
    handle = kernel.OpenProcess(_SYNCHRONIZE, False, pid)
    if not handle:
        return
    kernel.WaitForSingleObject(ctypes.c_void_p(handle), _WAIT_MS)
    kernel.CloseHandle(ctypes.c_void_p(handle))


def _replace(new: Path, exe: Path) -> bool:
    """Заменить exe скачанным, с повторами: свежий файл и только что закрытый exe
    ненадолго держит антивирус. Иная беда — скачанное пропало — повтором не
    лечится и уходит наверх."""
    for attempt in range(1, _ATTEMPTS + 1):
        try:
            os.replace(new, exe)
            logger.info("exe подменён: %s", exe)
            return True
        except PermissionError:
            logger.info("exe пока занят, попытка %d из %d", attempt, _ATTEMPTS)
            time.sleep(_PAUSE_SEC)
    logger.error("exe так и не подменился, запускается прежний: %s", exe)
    return False
