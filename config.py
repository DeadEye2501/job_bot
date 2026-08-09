"""Bootstrap config.

The DB path is derived from the OS user-data directory so the .exe
distribution doesn't need a `.env` file. All other settings live in the
SQLite database, populated by the first-run wizard via
``backend/runtime_settings.py``.
"""

import os
import sys
from pathlib import Path


APP_NAME = "JobBot"


def _user_data_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA")
        if base:
            return Path(base) / APP_NAME
        return Path.home() / "AppData" / "Roaming" / APP_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    base = os.environ.get("XDG_DATA_HOME")
    if base:
        return Path(base) / APP_NAME
    return Path.home() / ".local" / "share" / APP_NAME


def get_data_dir() -> Path:
    """Return (and create if missing) the per-user app-data directory."""
    path = _user_data_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_database_url() -> str:
    """Async SQLAlchemy URL for the local SQLite database."""
    db_file = get_data_dir() / "jobbot.db"
    return f"sqlite+aiosqlite:///{db_file.as_posix()}"


def get_log_path() -> Path:
    """Файл журнала — рядом с базой, а не рядом с приложением.

    Каталог приложения бывает недоступен на запись, а этот заведомо наш: в
    нём уже лежат база и вложения.
    """
    return get_data_dir() / "jobbot.log"
