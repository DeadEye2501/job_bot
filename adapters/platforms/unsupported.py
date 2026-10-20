"""Явный отказ до реализации macOS/Linux; WinAPI здесь не импортируется."""

import sys

SUPPORTS_UPDATES = False


class UnsupportedPlatformError(NotImplementedError):
    """Операция ещё не реализована для текущей ОС."""


def unavailable(*_args, **_kwargs):
    raise UnsupportedPlatformError(f"Системная операция не реализована для {sys.platform}")


has_window = tie_to_app = tie_children_named = unavailable
show_in_folder = open_target = show_trouble = unlock_frame = unavailable
cli_process_options = tie_browser_driver = unavailable
launch_updater = updater_copy = unavailable


def own_taskbar_icon() -> None:
    """На других ОС Windows-идентификатор панели задач не использовался."""


def allow_foreground() -> None:
    """Передача Windows-права фокуса на других ОС не требуется."""


def clear_leftovers() -> None:
    """На неподдержанной ОС не трогаем файлы рядом с executable."""


def run(_args: list[str]) -> int:
    """Режим --update не поддержан; не запускаем окно и не меняем файлы."""
    return 2


def find_browser():
    """До добавления реализации нет поддержанного установленного браузера."""
    return None


def lock_file(fd: int) -> None:
    """Существовавшая POSIX-блокировка не требует реализации GUI новой ОС."""
    import fcntl

    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
