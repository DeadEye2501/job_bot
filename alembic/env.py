"""Обвязка alembic: откуда берётся база и чьим движком идут миграции.

Заготовка alembic, правленная в трёх местах: адрес базы вычисляет `config` (в
оконной сборке файла настроек рядом нет), настройка журнала применяется не
всегда, движок берётся у `adapters/db` и закрывается под `finally`. Доводы
записаны у каждого места, здесь только счёт — чтобы правленое не искали по
всему файлу.
"""

import asyncio
import logging
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection

from adapters.db import make_engine
from backend.models import Base
from config import get_database_url

config = context.config
config.set_main_option("sqlalchemy.url", get_database_url())

# Настройка журнала из `alembic.ini` нужна только запуску из командной
# строки: там больше некому её сделать. Внутри приложения она вредна —
# `fileConfig` переписывает обработчики корневого logger'а целиком (root в
# `alembic.ini` перечислен явно), и приложение теряло после обновления схемы
# и файл журнала, и буфер экрана «Логи». Поэтому спрашиваем, настроен ли
# журнал уже: настроен — не трогаем.
if config.config_file_name is not None and not logging.getLogger().handlers:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    # Движок берётся у `adapters/db.py`, а не собирается здесь из секции
    # `alembic.ini`: своя сборка ставила бы схему и сеяла данные соединением
    # с чужими правилами, молча — расхождение видно не сразу, а на записанных
    # данных.
    connectable = make_engine(config.get_main_option("sqlalchemy.url"))
    # `dispose` под `finally`, потому что движок проекта держит пул: упавшая
    # на середине миграция иначе оставляет соединение живым, а вместе с ним —
    # занятый файл базы и спутники `-wal`/`-shm` рядом.
    try:
        async with connectable.connect() as connection:
            await connection.run_sync(do_run_migrations)
    finally:
        await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
