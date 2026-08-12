"""Database engine helpers (SQLite via aiosqlite)."""
import json

from sqlalchemy import event
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
    SQLAlchemy+SQLite-паттерн. Там же подменяется ``lower()``: встроенный
    складывает регистр только у латиницы.
    """
    engine = create_async_engine(database_url, json_serializer=_dump_json)

    @event.listens_for(engine.sync_engine, "connect")
    def _prepare_connection(dbapi_conn, _record):
        cursor = dbapi_conn.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
        finally:
            cursor.close()
        dbapi_conn.create_function("lower", 1, _lower, deterministic=True)

    return engine


def _lower(value: object) -> object:
    """LOWER() для SQLite, понимающий не только латиницу.

    Встроенный складывает регистр у одной латиницы: «Питон» остаётся
    «Питоном», а образец поиска питон опускает целиком, и совпасть им не на
    чем — вакансия с русским названием не находится ни одним написанием
    образца.

    Со встроенным сходится на строках и на пустоте, расходится на числах и
    двоичных данных: встроенный приводит их к тексту, эта отдаёт как есть.
    Расхождение недостижимо, пока под `func.lower` ходят только текстовые
    колонки, — а ходят сегодня только они.
    """
    return value.lower() if isinstance(value, str) else value
