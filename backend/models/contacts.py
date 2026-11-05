"""Таблицы сторон, с которыми связана вакансия."""

from datetime import datetime

from sqlalchemy import JSON, BigInteger, ForeignKey, Index, LargeBinary, false, func, text
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, column_property, mapped_column
from sqlalchemy.sql import expression

from backend.models.base import Base, IdMixin
from backend.models.workspace import (
    ACTIVE_WORKSPACE_ID,
    WorkspaceAggregator,
    WorkspaceChannel,
    switch_in,
)

# Тумблеры, отметки чтения и выбор резюме живут в строках «профиль × предмет»
# (`models/workspace.py`). Здесь под прежними именами — их значения в активном
# профиле: загружаемое поле под закрытым именем и гибрид поверх него без
# сеттера. Читатели не меняются, а забытый писатель падает `AttributeError`.
# После вставки строки поле не загружено: его догружает `load_switches`.


class TelegramChannel(IdMixin, Base):
    __tablename__ = "telegram_channel"

    username: Mapped[str | None]
    title: Mapped[str | None]
    avatar: Mapped[bytes | None] = mapped_column(LargeBinary)

    @hybrid_property
    def is_active(self) -> bool:
        return self._is_active

    @hybrid_property
    def last_processed_msg_id(self) -> int | None:
        return self._last_processed_msg_id


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
    is_logged_in: Mapped[bool] = mapped_column(server_default=expression.false())
    # Значок сайта — то же место, что аватар у канала: по нему агрегатор
    # узнают в списке, не читая имени.
    avatar: Mapped[bytes | None] = mapped_column(LargeBinary)
    can_add_resume: Mapped[bool] = mapped_column(server_default=expression.false())

    @hybrid_property
    def is_active(self) -> bool:
        return self._is_active

    @hybrid_property
    def last_run_at(self) -> datetime | None:
        return self._last_run_at


class AggregatorResume(IdMixin, Base):
    """Резюме человека на сайте агрегатора.

    Отмеченное в профиле — то, которым откликаться. Одно на сайт в профиле:
    его номер лежит в строке профиля (`WorkspaceAggregator.chosen_resume_id`).
    """

    __tablename__ = "aggregator_resume"
    __table_args__ = (
        Index("uq_aggregator_resume_url", "aggregator_id", "url", unique=True),
    )

    aggregator_id: Mapped[int] = mapped_column(ForeignKey("aggregator.id"))
    title: Mapped[str]
    url: Mapped[str]
    position: Mapped[int]

    @hybrid_property
    def is_chosen(self) -> bool:
        return self._is_chosen


TelegramChannel._is_active = column_property(func.coalesce(
    switch_in(WorkspaceChannel.is_active, WorkspaceChannel.channel_id, TelegramChannel.id,
              ACTIVE_WORKSPACE_ID),
    false(),
))
TelegramChannel._last_processed_msg_id = column_property(switch_in(
    WorkspaceChannel.last_processed_msg_id, WorkspaceChannel.channel_id, TelegramChannel.id,
    ACTIVE_WORKSPACE_ID,
))
Aggregator._is_active = column_property(func.coalesce(
    switch_in(WorkspaceAggregator.is_active, WorkspaceAggregator.aggregator_id, Aggregator.id,
              ACTIVE_WORKSPACE_ID),
    false(),
))
Aggregator._last_run_at = column_property(switch_in(
    WorkspaceAggregator.last_run_at, WorkspaceAggregator.aggregator_id, Aggregator.id,
    ACTIVE_WORKSPACE_ID,
))
AggregatorResume._is_chosen = column_property(func.coalesce(
    switch_in(WorkspaceAggregator.chosen_resume_id == AggregatorResume.id,
              WorkspaceAggregator.aggregator_id, AggregatorResume.aggregator_id,
              ACTIVE_WORKSPACE_ID),
    false(),
))


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
