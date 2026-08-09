"""Database engine helpers (SQLite via aiosqlite)."""
import json

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


def _dump_json(value: object) -> str:
    """Сериализация всех JSON-колонок без экранирования не-ASCII.

    По умолчанию `json.dumps` пишет кириллицу как `\\uXXXX`. Питону это
    безразлично — `json.loads` разбирает обе формы, — но записанное так
    недостижимо для поиска по приведённой к строке колонке: подстроки
    «тестирование» в записи `\\u0442\\u0435…` нет ни в каком регистре.
    """
    return json.dumps(value, ensure_ascii=False)


def make_engine(database_url: str) -> AsyncEngine:
    """Build the async engine + install per-connection SQLite PRAGMAs.

    SQLite ships с FK enforcement OFF, журналом DELETE и нулевым
    busy-timeout. На приложении с несколькими async-loop'ами (poll-loop,
    DM-listener, UI-bridge) это даёт «database is locked» ошибки и
    тихую порчу FK (например, ``TrashEvent.source_channel_id``
    декларирует ``ondelete=SET NULL``, но без FK enforcement остаётся
    висячий integer). Listener выпускает три PRAGMA при каждом новом
    соединении (включая connections из pool'а) — это стандартный
    SQLAlchemy+SQLite-паттерн.
    """
    engine = create_async_engine(database_url, json_serializer=_dump_json)

    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragmas(dbapi_conn, _record):
        cursor = dbapi_conn.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
        finally:
            cursor.close()

    return engine


async def check(engine: AsyncEngine) -> str:
    async with engine.connect() as conn:
        version = (
            await conn.execute(text("SELECT sqlite_version()"))
        ).scalar_one()
    return f"SQLite {version}"
