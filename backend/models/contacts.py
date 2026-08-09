"""Таблицы сторон, с которыми связана вакансия."""

from sqlalchemy import JSON, BigInteger, Index, LargeBinary, text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import expression

from backend.models.base import Base


class TelegramChannel(Base):
    __tablename__ = "telegram_channel"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str | None]
    title: Mapped[str | None]
    is_active: Mapped[bool] = mapped_column(server_default=expression.true())
    # BigInteger: Telegram message id может выйти за 2^31 в долгоживущих
    # массовых каналах. SQLite это проглатывает (INTEGER == 64bit), но
    # тип явно фиксирует контракт и переносит код на Postgres без сюрпризов.
    last_processed_msg_id: Mapped[int | None] = mapped_column(BigInteger)
    avatar: Mapped[bytes | None] = mapped_column(LargeBinary)


class HR(Base):
    __tablename__ = "hr"
    __table_args__ = (
        Index(
            "uq_hr_telegram_user_id",
            "telegram_user_id",
            unique=True,
            postgresql_where=text("telegram_user_id IS NOT NULL"),
            sqlite_where=text("telegram_user_id IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str | None]
    telegram_username: Mapped[str | None]
    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger)
    notes: Mapped[str | None]
    avatar: Mapped[bytes | None] = mapped_column(LargeBinary)


class Company(Base):
    __tablename__ = "company"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)
    aliases: Mapped[list[str]] = mapped_column(
        JSON, server_default=text("'[]'")
    )
    website: Mapped[str | None]
    notes: Mapped[str | None]
    avatar: Mapped[bytes | None] = mapped_column(LargeBinary)
