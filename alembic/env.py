import asyncio
import logging
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from backend.models import Base
from config import get_database_url

config = context.config
config.set_main_option("sqlalchemy.url", get_database_url())

if config.config_file_name is not None:
    # disable_existing_loggers=False — сохраняем уже сконфигурированные
    # логгеры. Но fileConfig всё равно ПЕРЕписывает handlers на root
    # (root явно перечислен в alembic.ini), поэтому LogBufferHandler
    # надо переставить вручную после fileConfig — иначе UI-логи
    # перестанут получать всё что логируется после миграций.
    fileConfig(config.config_file_name, disable_existing_loggers=False)
    try:
        from backend.log_buffer import install as _reinstall_log_buffer
        _reinstall_log_buffer()
    except Exception:
        # Не падаем если log_buffer переехал/сломался — миграция важнее
        # UI-логов, но молчать тоже нельзя: если это из-за ImportError'а,
        # юзер бы хотел знать что UI «Логи» больше не получит сообщений
        # после `alembic upgrade`.
        logging.getLogger(__name__).warning(
            "alembic env: failed to reinstall LogBufferHandler — "
            "in-app log panel will miss migration output",
            exc_info=True,
        )

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
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
