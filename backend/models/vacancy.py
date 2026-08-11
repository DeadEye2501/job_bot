"""Таблицы, в которых конвейер записывает судьбу разобранного поста."""

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import expression

from backend.models.base import Base, CreatedAtMixin, IdMixin, enum_column
from backend.models.contacts import HR, Company, TelegramChannel
from backend.models.enums import Currency, StatusHistorySource, VacancyStatus


class Vacancy(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "vacancy"
    # SQLite сам индексов на FK не создаёт — каждая отрисовка HR-карточки,
    # карточки компании, статистики канала иначе делает full-scan. Compound
    # (hr_id, is_parsed) и (company_id, is_parsed) покрывают самые горячие
    # фильтры UI-списка вакансий.
    __table_args__ = (
        UniqueConstraint(
            "source_channel_id",
            "source_msg_id",
            name="uq_vacancy_source",
        ),
        Index("ix_vacancy_hr_id", "hr_id"),
        Index("ix_vacancy_company_id", "company_id"),
        Index("ix_vacancy_source_channel_id", "source_channel_id"),
        Index("ix_vacancy_hr_id_is_parsed", "hr_id", "is_parsed"),
        Index("ix_vacancy_company_id_is_parsed", "company_id", "is_parsed"),
    )

    hr_id: Mapped[int | None] = mapped_column(ForeignKey("hr.id"))
    company_id: Mapped[int | None] = mapped_column(ForeignKey("company.id"))
    source_channel_id: Mapped[int | None] = mapped_column(
        ForeignKey("telegram_channel.id")
    )
    # BigInteger — см. TelegramChannel.last_processed_msg_id.
    source_msg_id: Mapped[int | None] = mapped_column(BigInteger)
    raw_text: Mapped[str | None]
    embedding: Mapped[list[float] | None] = mapped_column(JSON)
    title: Mapped[str | None]
    description: Mapped[str | None]
    company_name: Mapped[str | None]
    hr_contact: Mapped[str | None]
    stack: Mapped[list[str] | None] = mapped_column(JSON)
    grade: Mapped[str | None]
    salary: Mapped[str | None]
    salary_min: Mapped[int | None]
    salary_max: Mapped[int | None]
    salary_currency: Mapped[Currency | None] = mapped_column(
        enum_column(Currency, "currency")
    )
    remote: Mapped[str | None]
    location: Mapped[str | None]
    score: Mapped[int | None]
    skip_reason: Mapped[str | None]
    source_url: Mapped[str | None]
    status: Mapped[VacancyStatus] = mapped_column(
        enum_column(VacancyStatus, "vacancy_status"),
        server_default=text("'New'"),
    )
    # Flips to True only after the LLM parse + classify pipeline finishes
    # and persists structured fields (title, stack, score, ...). False
    # while the row holds just raw_text + embedding — i.e. it was created
    # by ``ingest.save_new_vacancy`` but the follow-up ``parse.parse_and_update_vacancy``
    # was killed (process crash, cancellation) before it could commit.
    # The UI list filters on ``is_parsed = True`` so users never see a
    # half-built row, and ``recover_orphan_vacancies`` re-parses the
    # ``False`` ones on the next startup before polling resumes.
    is_parsed: Mapped[bool] = mapped_column(server_default=expression.false())
    notes: Mapped[str | None]
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    hr: Mapped[HR | None] = relationship()
    company: Mapped[Company | None] = relationship()
    channel: Mapped[TelegramChannel | None] = relationship()


class VacancyEvent(IdMixin, CreatedAtMixin, Base):
    """Pipeline / lifecycle events for the timeline (non-status changes).

    Status transitions go to ``vacancy_status_history``; everything else
    (parsing OK, ingested-from-channel, etc.) goes here so the detail-pane
    timeline can render a full audit trail.
    """

    __tablename__ = "vacancy_event"
    __table_args__ = (
        Index("ix_vacancy_event_vacancy_created", "vacancy_id", "created_at"),
    )

    vacancy_id: Mapped[int] = mapped_column(ForeignKey("vacancy.id"))
    kind: Mapped[str]
    payload: Mapped[dict | None] = mapped_column(JSON)


class TrashEvent(IdMixin, CreatedAtMixin, Base):
    """Запись о посте, отсеянном LLM-валидатором как trash и удалённом
    из БД (auto-ingest) либо помеченном Not Fit с trash-маркером (rerun).

    Зачем нужно: в auto-ingest режиме «trash» вакансии полностью удаляются
    из ``vacancy``, и впоследствии посчитать «сколько канал прислал мусора
    за период» по ``Vacancy``-ряду нельзя. Эта таблица — независимый
    счётчик: пишем по одной строке на каждый акт классификации поста как
    trash, привязываем к каналу. Per-period stats по каналам читают её
    через COUNT(*) WHERE channel_id=X AND created_at >= since.

    Поля:
      - source_channel_id: nullable FK на ``telegram_channel`` (если канал
        удалён, событие остаётся «orphan» — статистика всё равно посчитает
        в общий лайфтайм)
      - source_msg_id: id поста в Telegram. Не уникальное (бот может
        несколько раз увидеть один и тот же пост в разных условиях), но
        полезно для debug
      - reason: краткий текст вердикта валидатора (LLM-причина) или
        ``"empty"`` для пустых вакансий без структуры
    """

    __tablename__ = "trash_event"
    __table_args__ = (
        Index("ix_trash_event_channel_created", "source_channel_id", "created_at"),
    )

    source_channel_id: Mapped[int | None] = mapped_column(
        ForeignKey("telegram_channel.id", ondelete="SET NULL"),
    )
    source_msg_id: Mapped[int | None] = mapped_column(BigInteger)
    reason: Mapped[str | None]


class VacancyStatusHistory(IdMixin, Base):
    __tablename__ = "vacancy_status_history"
    __table_args__ = (
        Index("ix_vsh_vacancy_changed", "vacancy_id", "changed_at"),
        # Aggregate-запросы по статусу (Applied / Decline counters в stats)
        # сканировали всю таблицу — теперь по индексу.
        Index("ix_vsh_status", "status"),
    )

    vacancy_id: Mapped[int] = mapped_column(ForeignKey("vacancy.id"))
    message_id: Mapped[int | None] = mapped_column(ForeignKey("message.id"))
    previous_status: Mapped[VacancyStatus | None] = mapped_column(
        enum_column(VacancyStatus, "vacancy_status", create_type=False),
    )
    status: Mapped[VacancyStatus] = mapped_column(
        enum_column(VacancyStatus, "vacancy_status", create_type=False),
    )
    # Без explicit length — все остальные строковые поля в схеме объявлены
    # как `String` (SQLite всё равно хранит TEXT без cap'а на длину).
    # 2000-cap раньше отличал эту колонку без причины. Ограничение длины
    # на стороне приложения — `_ensure_trailing_period` в repository/vacancies_life.py
    # сам обрабатывает None/empty; UI textarea имеет maxlength=2000.
    explanation: Mapped[str | None] = mapped_column(String)
    applied: Mapped[bool] = mapped_column(server_default=expression.true())
    source: Mapped[StatusHistorySource] = mapped_column(
        enum_column(StatusHistorySource, "status_history_source"),
        server_default=text("'system'"),
    )
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
