"""Database engine helpers (SQLite via aiosqlite)."""
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


def make_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(database_url)


async def check(engine: AsyncEngine) -> str:
    async with engine.connect() as conn:
        version = (
            await conn.execute(text("SELECT sqlite_version()"))
        ).scalar_one()
    return f"SQLite {version}"
