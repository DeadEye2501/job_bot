"""Где на маке лежат программы, которые приложение зовёт по имени.

Приложение, открытое из Finder, получает урезанный `PATH`
(`/usr/bin:/bin:/usr/sbin:/sbin`), и Claude Code, поставленный в домашний
каталог или Homebrew, «не установлен». Известные места дописываются в конец:
порядок, заданный самим человеком при запуске из терминала, остаётся первым.
"""

import os
from pathlib import Path


def _places() -> list[Path]:
    home = Path.home()
    return [home / ".local" / "bin", home / ".claude" / "local", Path("/opt/homebrew/bin"),
            Path("/usr/local/bin")]


def with_install_places(path: str) -> str:
    """`path` с дописанными в конец существующими местами установки, без повторов."""
    named = path.split(os.pathsep) if path else []
    extra = [str(place) for place in _places() if place.is_dir() and str(place) not in named]
    return os.pathsep.join(named + extra)


def widen_path() -> None:
    """Дописать места установки в `PATH` своего процесса и его детей."""
    os.environ["PATH"] = with_install_places(os.environ.get("PATH", ""))
