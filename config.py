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


LOG_KEPT = 3
"""Сколько повёрнутых копий журнала хранится рядом с ним.

Объявлено здесь, а не у настройки журнала: копии — такая же часть каталога
данных, как и сам журнал, и снос обязан знать про них. Разъедься это число с
тем, по которому журнал поворачивается, — «удалить всё» оставило бы на диске
переписку человека в старых копиях.
"""

_DB_NAME = "jobbot.db"
"""Имя файла базы. Одно на весь проект: его знают и адрес подключения, и снос
данных, и по нему же ищутся спутники журнального режима.
"""


def get_database_url() -> str:
    """Async SQLAlchemy URL for the local SQLite database."""
    db_file = get_data_dir() / _DB_NAME
    return f"sqlite+aiosqlite:///{db_file.as_posix()}"


def get_lock_path() -> Path:
    """Файл, на котором держится замок единственной копии.

    Лежит там же, где база и журнал, — ровно потому, что сторожит их: копии,
    поделившие один каталог данных, и мешают друг другу, а запущенные над
    разными каталогами не мешают вовсе.
    """
    return get_data_dir() / "jobbot.lock"


def data_files() -> list[Path]:
    """Файлы, которые приложение держит в каталоге данных.

    Одно объявление на всех, кто про этот каталог спрашивает: снос данных
    прежде собирал те же имена строками у себя и знал их пять из семи —
    журнал и замок оставались на диске после «удалить всё».

    Спутники базы (`-shm`, `-wal`) появляются от журнального режима SQLite
    (`adapters/db.py`), и без них снос оставляет базу восстановимой.
    """
    data_dir = get_data_dir()
    db = data_dir / _DB_NAME
    return [
        db,
        db.with_name(db.name + "-shm"),
        db.with_name(db.name + "-wal"),
        get_lock_path(),
        *_log_files(),
    ]


def _log_files() -> list[Path]:
    """Журнал и его повёрнутые копии — `jobbot.log`, `jobbot.log.1` и так далее."""
    log = get_log_path()
    return [log, *(log.with_name(f"{log.name}.{n}") for n in range(1, LOG_KEPT + 1))]


def data_dirs() -> list[Path]:
    """Папки, которые приложение держит в каталоге данных.

    Имена объявлены не здесь, а там, где эти папки заводятся, — у сеансов
    Telegram и у вложений; здесь только перечень для тех, кому нужен весь
    каталог целиком.

    Берётся из объявлений имя, а путь собирается заново: те объявления
    считаются один раз, при ввозе модуля, и за сменившимся каталогом данных не
    идут. Ввоз отложен в тело по той же причине, по какой эти модули ввозят
    `config`: наверху вышел бы круг.
    """
    from adapters.telegram import SESSIONS_DIR
    from backend.bot.media import MEDIA_DIR

    data_dir = get_data_dir()
    return [data_dir / SESSIONS_DIR.name, data_dir / MEDIA_DIR.name]


def get_log_path() -> Path:
    """Файл журнала — рядом с базой, а не рядом с приложением.

    Каталог приложения бывает недоступен на запись, а этот заведомо наш: в
    нём уже лежат база и вложения.
    """
    return get_data_dir() / "jobbot.log"
