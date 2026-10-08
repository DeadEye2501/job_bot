"""Дочерние процессы, которые Windows снимает вместе с приложением.

Обычное закрытие окна снимает живой Claude Code само
(`claude_code_process.shutdown`), но приложение умирает и иначе — падением,
снятием из диспетчера задач. Тогда гасить некому, и процесс висел бы, держа
память. Задание Windows с флагом «снять всё при закрытии» держит само
приложение: умерло оно любым путём — система закрывает задание и снимает
всех, кто к нему привязан.
"""

import ctypes
import logging
import sys
from ctypes import wintypes

_log = logging.getLogger(__name__)

_KILL_ON_JOB_CLOSE = 0x2000
_EXTENDED_LIMIT_INFORMATION = 9
_PROCESS_SET_QUOTA = 0x0100
_PROCESS_TERMINATE = 0x0001


class _IoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint64) for name in (
        "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
        "ReadTransferCount", "WriteTransferCount", "OtherTransferCount",
    )]


class _BasicLimit(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _ExtendedLimit(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _BasicLimit),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


# Задание приложения: создаётся с первым привязанным процессом и живёт, пока
# живёт приложение, — его закрытие и есть сигнал системе снять привязанных.
_job = None


def _kernel32():
    """Функции Windows с честными типами: дескриптор не влез бы в `int` по умолчанию."""
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateJobObjectW.restype = wintypes.HANDLE
    k.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    k.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    k.OpenProcess.restype = wintypes.HANDLE
    k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    k.CloseHandle.argtypes = [wintypes.HANDLE]
    return k


def _kill_on_close_job():
    """Новое задание, которое при закрытии снимает все свои процессы."""
    k = _kernel32()
    job = k.CreateJobObjectW(None, None)
    if not job:
        raise ctypes.WinError(ctypes.get_last_error())
    info = _ExtendedLimit()
    info.BasicLimitInformation.LimitFlags = _KILL_ON_JOB_CLOSE
    if not k.SetInformationJobObject(
        job, _EXTENDED_LIMIT_INFORMATION, ctypes.byref(info), ctypes.sizeof(info)
    ):
        error = ctypes.get_last_error()
        k.CloseHandle(job)
        raise ctypes.WinError(error)
    return job


def _assign(job, pid: int) -> None:
    """Привязать процесс к заданию."""
    k = _kernel32()
    process = k.OpenProcess(_PROCESS_SET_QUOTA | _PROCESS_TERMINATE, False, pid)
    if not process:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        if not k.AssignProcessToJobObject(job, process):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        k.CloseHandle(process)


def tie_to_app(pid: int) -> None:
    """Привязать процесс к приложению: Windows снимет его, когда приложение умрёт.

    Не вышло — запись в журнал, а процесс живёт как был: обычное закрытие окна
    снимет его и так, без привязки он переживёт лишь аварийный выход.
    """
    global _job
    if sys.platform != "win32":
        return
    try:
        if _job is None:
            _job = _kill_on_close_job()
        _assign(_job, pid)
    except OSError:
        _log.exception("процесс %s не привязан к приложению", pid)
