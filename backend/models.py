import enum
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Index,
    JSON,
    LargeBinary,
    String,
    Table,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import expression


class Base(DeclarativeBase):
    pass


class BotMode(enum.Enum):
    OFF = "Off"
    DM_ONLY = "DM Only"
    FULL = "Full"


class VacancyStatus(enum.Enum):
    NEW = "New"
    APPLIED = "Applied"
    ANSWERED = "Answered"
    TEST = "Test"
    INVITATION = "Invitation"
    IN_PROGRESS = "In Progress"
    DECLINE = "Decline"
    GHOSTING = "Ghosting"
    SCAM = "Scam"
    NOT_FIT = "Not Fit"
    OFFER = "Offer"


class StatusHistorySource(enum.Enum):
    """Кто сгенерировал запись в vacancy_status_history.

    SYSTEM — авто-классификация HR-реплая, авто-/ручная отправка отклика
    ботом, любые системные источники. Текст в ``explanation`` сгенерирован
    кодом или LLM, юзер его не писал.
    USER — пользователь руками сменил статус через UI, ``explanation``
    введён юзером и должен быть редактируемым."""

    SYSTEM = "system"
    USER = "user"


class LlmConfigKind(enum.Enum):
    CHAT = "chat"
    EMBED = "embed"


profile_experience_skills = Table(
    "profile_experience_skills",
    Base.metadata,
    Column("experience_id", ForeignKey("profile_experience.id"), primary_key=True),
    Column("skill_id", ForeignKey("profile_skills.id"), primary_key=True),
)


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


class Profile(Base):
    __tablename__ = "profile"

    id: Mapped[int] = mapped_column(primary_key=True)
    first_name: Mapped[str]
    last_name: Mapped[str]
    title: Mapped[str]
    email: Mapped[str]
    phone: Mapped[str | None]
    location: Mapped[str | None]
    telegram_username: Mapped[str | None]
    github_url: Mapped[str | None]
    education: Mapped[str | None]
    work_format: Mapped[list[str]] = mapped_column(
        JSON, server_default=text("'[]'")
    )  # подмножество {"office","remote","hybrid"}
    grades: Mapped[list[str]] = mapped_column(
        JSON, server_default=text("'[]'")
    )  # подмножество {"junior","middle","senior","lead"}
    free_preferences: Mapped[str | None]

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class ProfileLanguage(Base):
    """Языки кандидата с уровнем владения для LLM-валидации.

    Один профиль — несколько языков (Русский native, Английский B1, и т.д.).
    Уровень — стандартный CEFR + "native". В промпт подмешивается строкой
    "Русский — native, Английский — B1, Армянский — A2".

    Уникальность по (profile_id, language) — нельзя дважды добавить тот
    же язык; редактирование = upsert по этой паре.
    """

    __tablename__ = "profile_language"
    __table_args__ = (
        UniqueConstraint("profile_id", "language"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profile.id"))
    language: Mapped[str]
    level: Mapped[str]  # "A1" | "A2" | "B1" | "B2" | "C1" | "C2" | "native"


class ProfileSkill(Base):
    __tablename__ = "profile_skills"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profile.id"))
    category: Mapped[str]
    name: Mapped[str]
    level: Mapped[int]
    aliases: Mapped[list[str]] = mapped_column(
        JSON, server_default=text("'[]'")
    )


class ProfileExperience(Base):
    __tablename__ = "profile_experience"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profile.id"))
    company: Mapped[str]
    company_url: Mapped[str | None]
    role: Mapped[str]
    start_date: Mapped[date]
    end_date: Mapped[date | None]
    achievements: Mapped[list[str]] = mapped_column(
        JSON, server_default=text("'[]'")
    )
    responsibilities: Mapped[list[str]] = mapped_column(
        JSON, server_default=text("'[]'")
    )
    skills: Mapped[list["ProfileSkill"]] = relationship(
        secondary=profile_experience_skills
    )


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


class Vacancy(Base):
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

    id: Mapped[int] = mapped_column(primary_key=True)
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
    salary_rub_min: Mapped[int | None]
    salary_rub_max: Mapped[int | None]
    remote: Mapped[str | None]
    location: Mapped[str | None]
    score: Mapped[int | None]
    skip_reason: Mapped[str | None]
    source_url: Mapped[str | None]
    status: Mapped[VacancyStatus] = mapped_column(
        SQLEnum(
            VacancyStatus,
            values_callable=lambda x: [e.value for e in x],
            name="vacancy_status",
        ),
        server_default=text("'New'"),
    )
    # Flips to True only after the LLM parse + classify pipeline finishes
    # and persists structured fields (title, stack, score, ...). False
    # while the row holds just raw_text + embedding — i.e. it was created
    # by ``_save_new_vacancy`` but the follow-up ``_parse_and_update_vacancy``
    # was killed (process crash, cancellation) before it could commit.
    # The UI list filters on ``is_parsed = True`` so users never see a
    # half-built row, and ``recover_orphan_vacancies`` re-parses the
    # ``False`` ones on the next startup before polling resumes.
    is_parsed: Mapped[bool] = mapped_column(server_default=expression.false())
    notes: Mapped[str | None]
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    hr: Mapped["HR | None"] = relationship()
    company: Mapped["Company | None"] = relationship()
    channel: Mapped["TelegramChannel | None"] = relationship()


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


class Message(Base):
    __tablename__ = "message"
    # FK-индексы на hr_id / vacancy_id горячие: chat-list, HR-detail,
    # vacancy-delete-cascade ходят по ним в каждом UI-action'е.
    __table_args__ = (
        UniqueConstraint(
            "hr_id",
            "tg_message_id",
            "is_incoming",
            name="uq_message_hr_tgid_dir",
        ),
        Index("ix_message_hr_id", "hr_id"),
        Index("ix_message_vacancy_id", "vacancy_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    is_incoming: Mapped[bool] = mapped_column(server_default=expression.false())
    hr_id: Mapped[int | None] = mapped_column(ForeignKey("hr.id"))
    vacancy_id: Mapped[int | None] = mapped_column(ForeignKey("vacancy.id"))
    text: Mapped[str]
    tg_message_id: Mapped[int | None]
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    # NULL = unread. For incoming: when WE marked it read in the app /
    # Pyrogram. For outgoing: when the HR read it (set by
    # ``UpdateReadHistoryOutbox`` raw handler). The unread badge only counts
    # incoming.
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Pyrogram raw-update flags. Edits overwrite ``text`` AND set is_edited;
    # deletes set is_deleted but keep the row + original text so the chat
    # can show a «(удалено)» marker without losing history.
    is_edited: Mapped[bool] = mapped_column(server_default=expression.false())
    is_deleted: Mapped[bool] = mapped_column(server_default=expression.false())
    # Media attachment, if any. ``media_kind`` is one of "photo" / "document"
    # (other Telegram media types are skipped — out of scope for this bot).
    # ``media_path`` is a project-relative cached path under ``media/``.
    # ``media_name`` keeps the original document filename for the UI link.
    media_kind: Mapped[str | None]
    media_path: Mapped[str | None]
    media_name: Mapped[str | None]


class VacancyEvent(Base):
    """Pipeline / lifecycle events for the timeline (non-status changes).

    Status transitions go to ``vacancy_status_history``; everything else
    (parsing OK, ingested-from-channel, etc.) goes here so the detail-pane
    timeline can render a full audit trail.
    """

    __tablename__ = "vacancy_event"
    __table_args__ = (
        Index("ix_vacancy_event_vacancy_created", "vacancy_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    vacancy_id: Mapped[int] = mapped_column(ForeignKey("vacancy.id"))
    kind: Mapped[str]
    payload: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )


class TrashEvent(Base):
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

    id: Mapped[int] = mapped_column(primary_key=True)
    source_channel_id: Mapped[int | None] = mapped_column(
        ForeignKey("telegram_channel.id", ondelete="SET NULL"),
    )
    source_msg_id: Mapped[int | None] = mapped_column(BigInteger)
    reason: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )


class VacancyStatusHistory(Base):
    __tablename__ = "vacancy_status_history"
    __table_args__ = (
        Index("ix_vsh_vacancy_changed", "vacancy_id", "changed_at"),
        # Aggregate-запросы по статусу (Applied / Decline counters в stats)
        # сканировали всю таблицу — теперь по индексу.
        Index("ix_vsh_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    vacancy_id: Mapped[int] = mapped_column(ForeignKey("vacancy.id"))
    message_id: Mapped[int | None] = mapped_column(ForeignKey("message.id"))
    previous_status: Mapped[VacancyStatus | None] = mapped_column(
        SQLEnum(
            VacancyStatus,
            values_callable=lambda x: [e.value for e in x],
            name="vacancy_status",
            create_type=False,
        ),
    )
    status: Mapped[VacancyStatus] = mapped_column(
        SQLEnum(
            VacancyStatus,
            values_callable=lambda x: [e.value for e in x],
            name="vacancy_status",
            create_type=False,
        ),
    )
    # Без explicit length — все остальные строковые поля в схеме объявлены
    # как `String` (SQLite всё равно хранит TEXT без cap'а на длину).
    # 2000-cap раньше отличал эту колонку без причины. Ограничение длины
    # на стороне приложения — `_ensure_trailing_period` в repository.py
    # сам обрабатывает None/empty; UI textarea имеет maxlength=2000.
    explanation: Mapped[str | None] = mapped_column(String)
    applied: Mapped[bool] = mapped_column(server_default=expression.true())
    source: Mapped[StatusHistorySource] = mapped_column(
        SQLEnum(
            StatusHistorySource,
            values_callable=lambda x: [e.value for e in x],
            name="status_history_source",
        ),
        server_default=text("'system'"),
    )
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )


# === Settings tables (filled at runtime, mostly via the first-run wizard) ===


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
