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
import os
import sys
from ctypes import wintypes

_log = logging.getLogger(__name__)

_KILL_ON_JOB_CLOSE = 0x2000
_EXTENDED_LIMIT_INFORMATION = 9
_PROCESS_SET_QUOTA = 0x0100
_PROCESS_TERMINATE = 0x0001
_SNAPPROCESS = 0x2
_INVALID_HANDLE = wintypes.HANDLE(-1).value


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


class _ProcessEntry(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", ctypes.c_wchar * 260),
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
    k.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    k.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    k.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ProcessEntry)]
    k.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ProcessEntry)]
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


def tie_children_named(name: str) -> int:
    """Привязать дочерние процессы приложения с этим именем. Ответ — сколько привязано.

    Публичного способа узнать процесс драйвера Playwright нет. Свой процесс
    приложение не привязывает: привязку унаследовало бы и открытое «системой» —
    браузер и программы человека погасли бы вместе с приложением.
    """
    count = 0
    for pid, image in _children():
        if image.lower() == name.lower():
            tie_to_app(pid)
            count += 1
    return count


def _children() -> list[tuple[int, str]]:
    """Дочерние процессы приложения: номер и имя файла — по снимку процессов Windows.

    Неудача снимка — запись в журнал и пустой список: исход тот же, что у
    несостоявшейся привязки, работе он не мешает.
    """
    if sys.platform != "win32":
        return []
    try:
        return [(pid, image) for pid, parent, image in _snapshot() if parent == os.getpid()]
    except OSError:
        _log.exception("дочерние процессы приложения не перечислены")
        return []


def _snapshot() -> list[tuple[int, int, str]]:
    """Все процессы системы: номер, номер родителя, имя файла."""
    k = _kernel32()
    snapshot = k.CreateToolhelp32Snapshot(_SNAPPROCESS, 0)
    if snapshot == _INVALID_HANDLE:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        entry = _ProcessEntry(dwSize=ctypes.sizeof(_ProcessEntry))
        found = []
        more = k.Process32FirstW(snapshot, ctypes.byref(entry))
        while more:
            found.append((entry.th32ProcessID, entry.th32ParentProcessID, entry.szExeFile))
            more = k.Process32NextW(snapshot, ctypes.byref(entry))
        return found
    finally:
        k.CloseHandle(snapshot)
