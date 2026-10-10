"""Отклик и скрининг по нему."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base, CreatedAtMixin, IdMixin, enum_column
from backend.models.enums import ApplicationVia


class Application(IdMixin, Base):
    """Отклик, ушедший в Telegram, на сайте агрегатора, формой работодателя или письмом.

    Пишется только состоявшимся. Чат и его якорь живут здесь, а не на вакансии:
    у двух откликов одной вакансии два чата.
    """

    __tablename__ = "application"
    __table_args__ = (Index("ix_application_vacancy_id", "vacancy_id"),)

    vacancy_id: Mapped[int] = mapped_column(ForeignKey("vacancy.id"))
    aggregator_id: Mapped[int | None] = mapped_column(
        ForeignKey("aggregator.id"),
    )
    via: Mapped[ApplicationVia] = mapped_column(
        enum_column(ApplicationVia, "application_via")
    )
    target: Mapped[str]
    letter: Mapped[str | None]
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    chat_anchor: Mapped[str | None]


class Screening(IdMixin, CreatedAtMixin, Base):
    """Реплика скрининга по отклику: вопрос работодателя или наш ответ."""

    __tablename__ = "screening"
    __table_args__ = (
        Index("uq_screening_position", "application_id", "position", unique=True),
    )

    application_id: Mapped[int] = mapped_column(ForeignKey("application.id"))
    from_us: Mapped[bool]
    text: Mapped[str]
    position: Mapped[int]
