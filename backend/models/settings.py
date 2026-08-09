"""Таблицы, которыми настраивают работу бота."""

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum as SQLEnum,
    LargeBinary,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import expression

from backend.models.base import Base
from backend.models.enums import BotMode, LlmConfigKind


class BotState(Base):
    """Single-row table — id всегда 1. CHECK-constraint защищает от
    случайной вставки второй строки через raw SQL: ``runtime_settings``
    хардкодит id=1 в setter'ах, но без БД-уровневой защиты ``get_mode``
    при наличии лишних строк возвращал бы недетерминированную."""

    __tablename__ = "bot_state"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_bot_state_singleton"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    mode: Mapped[BotMode] = mapped_column(
        SQLEnum(
            BotMode,
            values_callable=lambda x: [e.value for e in x],
            name="bot_mode",
        ),
        server_default=text("'Off'"),
    )


class Blacklist(Base):
    __tablename__ = "blacklist"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str]
    value: Mapped[str]
    reason: Mapped[str | None]
    active: Mapped[bool] = mapped_column(server_default=expression.true())
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )


class TgAccount(Base):
    """Single-row table holding the active Telegram account.

    Encrypted columns store ciphertext produced by the Python-side Fernet
    wrapper using the master key from the OS keyring. CHECK-constraint
    enforces id=1 на уровне БД — см. ``BotState`` для мотивации.
    """

    __tablename__ = "tg_account"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_tg_account_singleton"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    api_id: Mapped[int | None]
    api_hash_encrypted: Mapped[str | None]
    phone: Mapped[str | None]
    password_encrypted: Mapped[str | None]
    session_blob_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class LlmConfig(Base):
    """OpenAI-compatible LLM endpoint config. Two rows: kind=chat, kind=embed."""

    __tablename__ = "llm_config"
    __table_args__ = (
        UniqueConstraint("kind", name="uq_llm_config_kind"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[LlmConfigKind] = mapped_column(
        SQLEnum(
            LlmConfigKind,
            values_callable=lambda x: [e.value for e in x],
            name="llm_config_kind",
        ),
    )
    base_url: Mapped[str | None]
    api_key_encrypted: Mapped[str | None]
    model: Mapped[str | None]
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class AppSetting(Base):
    """Generic key-value runtime tunables. Plaintext values only."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(primary_key=True)
    value: Mapped[str | None]
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
