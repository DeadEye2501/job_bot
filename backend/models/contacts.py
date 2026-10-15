"""Таблицы сторон, с которыми связана вакансия."""

from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, Index, LargeBinary, text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import expression

from backend.models.base import Base, IdMixin


class TelegramChannel(IdMixin, Base):
    __tablename__ = "telegram_channel"

    username: Mapped[str | None]
    title: Mapped[str | None]
    is_active: Mapped[bool] = mapped_column(server_default=expression.true())
    # BigInteger: Telegram message id может выйти за 2^31 в долгоживущих
    # массовых каналах. SQLite это проглатывает (INTEGER == 64bit), но
    # тип явно фиксирует контракт и переносит код на Postgres без сюрпризов.
    last_processed_msg_id: Mapped[int | None] = mapped_column(BigInteger)
    avatar: Mapped[bytes | None] = mapped_column(LargeBinary)


class Aggregator(IdMixin, Base):
    """Сайт-агрегатор как источник вакансий, и строка «Поиск по сети».

    Пустой хост бывает только у строки «Поиск по сети». Уникальный индекс
    пустые значения не ловит: вторую такую строку не заводит код, а не база.
    Входа в базе нет — только отметка, что человек вошёл на сайт в браузере.
    """

    __tablename__ = "aggregator"
    __table_args__ = (Index("uq_aggregator_host", "host", unique=True),)

    name: Mapped[str]
    host: Mapped[str | None]
    is_active: Mapped[bool] = mapped_column(server_default=expression.false())
    is_logged_in: Mapped[bool] = mapped_column(server_default=expression.false())
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Значок сайта — то же место, что аватар у канала: по нему агрегатор
    # узнают в списке, не читая имени.
    avatar: Mapped[bytes | None] = mapped_column(LargeBinary)
    can_add_resume: Mapped[bool] = mapped_column(server_default=expression.false())


class AggregatorResume(IdMixin, Base):
    """Резюме человека на сайте агрегатора.

    Отмеченное — то, которым откликаться. Больше одного отмеченного на сайте
    база не примет: какое из двух брать, иначе решал бы случай.
    """

    __tablename__ = "aggregator_resume"
    __table_args__ = (
        Index("uq_aggregator_resume_url", "aggregator_id", "url", unique=True),
        Index(
            "uq_aggregator_resume_chosen",
            "aggregator_id",
            unique=True,
            postgresql_where=text("is_chosen"),
            sqlite_where=text("is_chosen"),
        ),
    )

    aggregator_id: Mapped[int] = mapped_column(ForeignKey("aggregator.id"))
    title: Mapped[str]
    url: Mapped[str]
    # Адрес правки именно этого резюме: страница резюме и его редактор на
    # сайтах разные, и перезапись начинается с редактора, а не с поиска по сайту.
    editor_url: Mapped[str | None]
    position: Mapped[int]
    is_chosen: Mapped[bool] = mapped_column(server_default=expression.false())


class HR(IdMixin, Base):
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

    name: Mapped[str | None]
    telegram_username: Mapped[str | None]
    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger)
    notes: Mapped[str | None]
    avatar: Mapped[bytes | None] = mapped_column(LargeBinary)


class Company(IdMixin, Base):
    __tablename__ = "company"

    name: Mapped[str] = mapped_column(unique=True)
    aliases: Mapped[list[str]] = mapped_column(
        JSON, server_default=text("'[]'")
    )
    website: Mapped[str | None]
    notes: Mapped[str | None]
    avatar: Mapped[bytes | None] = mapped_column(LargeBinary)
