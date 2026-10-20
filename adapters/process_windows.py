"""Видимые окна процесса Windows.

По ним видно, закрыл ли человек программу, которая после закрытия окна живёт
в фоне: конец процесса этого не говорит.
"""

import ctypes
from ctypes import wintypes

_EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def has_window(pid: int) -> bool:
    """Есть ли у процесса видимое окно верхнего уровня."""
    user32 = ctypes.WinDLL("user32")
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    found = False

    def look(window, _param) -> bool:
        nonlocal found
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(window, ctypes.byref(owner))
        found = owner.value == pid and bool(user32.IsWindowVisible(window))
        return not found

    user32.EnumWindows(_EnumProc(look), 0)
    return found
