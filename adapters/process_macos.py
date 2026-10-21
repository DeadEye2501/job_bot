"""Окна процесса на маке — двойник `process_windows`.

По ним видно, закрыл ли человек программу, которая после закрытия окна живёт
в фоне: конец процесса этого не говорит. Свёрнутое окно и окно на другом
рабочем столе считаются: Windows-оригинал спрашивает `IsWindowVisible`, а она
истинна и у свёрнутого.
"""

_NORMAL_LAYER = 0


def has_window(pid: int) -> bool:
    """Есть ли у процесса окно обычного слоя — на экране, свёрнутое или на другом столе."""
    import Quartz

    windows = Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionAll, Quartz.kCGNullWindowID)
    return any(
        window.get("kCGWindowOwnerPID") == pid and window.get("kCGWindowLayer") == _NORMAL_LAYER
        for window in windows
    )
