"""Таблицы, которыми настраивают работу бота."""

from sqlalchemy import (
    CheckConstraint,
    ColumnElement,
    LargeBinary,
    UniqueConstraint,
    exists,
    false,
    func,
    text,
)
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, column_property, mapped_column

from backend.models.base import (
    Base,
    CreatedAtMixin,
    IdMixin,
    UpdatedAtMixin,
    enum_column,
)
from backend.models.enums import BotMode, LlmConfigKind
from backend.models.workspace import ACTIVE_WORKSPACE_ID, WorkspaceBlacklist, switch_in


class BotState(IdMixin, Base):
    """Единственная строка состояния — id всегда 1.

    CHECK-constraint защищает от случайной вставки второй строки сырым SQL:
    запись режима (`repository/bot_mode`) хардкодит id=1, но чтение берёт
    первую попавшуюся, и при лишних строках отвечало бы наугад."""

    __tablename__ = "bot_state"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_bot_state_singleton"),
    )

    mode: Mapped[BotMode] = mapped_column(
        enum_column(BotMode, "bot_mode"),
        server_default=text("'Off'"),
    )


# `Blacklist.kind` — свободная строка: отсеять чужое значение может только
# код. Здесь набор объявлен для бэкенда; второе его написание живёт во фронте
# (`BLACKLIST_KINDS` в `client/web/state/blacklist.js`) и несёт ещё и слова для
# человека. Сойтись они обязаны ключами: род, известный одному и неизвестный
# другому, даёт строку, которую заводят, но не показывают. Каждый род назван
# своим именем, и бэкенд пишет его только так: опечатка в литерале не нашлась
# бы ничем, кроме отметки, которая молча перестала отмечать.
KEYWORD_KIND = "keyword"
HR_KIND = "hr"
COMPANY_KIND = "company"
CHANNEL_KIND = "channel"
AGGREGATOR_KIND = "aggregator"
BLACKLIST_KINDS: tuple[str, ...] = (
    KEYWORD_KIND, HR_KIND, COMPANY_KIND, CHANNEL_KIND, AGGREGATOR_KIND
)


class Blacklist(IdMixin, CreatedAtMixin, Base):
    """Запись чёрного списка — общая; включена ли она, решает каждый профиль.

    `active` — включённость в активном профиле, только для чтения: пишут её
    через строку профиля (`workspace_switches.put_switch`).
    """

    __tablename__ = "blacklist"

    kind: Mapped[str]
    value: Mapped[str]
    reason: Mapped[str | None]

    @hybrid_property
    def active(self) -> bool:
        return self._active


def blacklist_on(workspace: int | ColumnElement[int]) -> ColumnElement[bool]:
    """Условие «строка списка включена в этом профиле»; `workspace` — номер
    или `ACTIVE_WORKSPACE_ID`. Строки профиля нет — выключена."""
    return func.coalesce(
        switch_in(WorkspaceBlacklist.active, WorkspaceBlacklist.blacklist_id, Blacklist.id,
                  workspace),
        false(),
    )


def blacklist_on_anywhere() -> ColumnElement[bool]:
    """Условие «строка списка включена хотя бы в одном профиле»."""
    return exists().where(
        WorkspaceBlacklist.blacklist_id == Blacklist.id, WorkspaceBlacklist.active
    )


Blacklist._active = column_property(blacklist_on(ACTIVE_WORKSPACE_ID))


class TgAccount(IdMixin, UpdatedAtMixin, Base):
    """Single-row table holding the active Telegram account.

    Encrypted columns store ciphertext produced by the Python-side Fernet
    wrapper using the master key from the OS keyring. CHECK-constraint
    enforces id=1 на уровне БД — см. ``BotState`` для мотивации.
    """

    __tablename__ = "tg_account"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_tg_account_singleton"),
    )

    api_id: Mapped[int | None]
    api_hash_encrypted: Mapped[str | None]
    phone: Mapped[str | None]
    password_encrypted: Mapped[str | None]
    session_blob_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary)


class MailAccount(IdMixin, UpdatedAtMixin, Base):
    """Почта, с которой уходят отклики письмом. Только отправка по SMTP.

    Пароль приложения шифруется тем же Fernet, что секреты Telegram.
    """

    __tablename__ = "mail_account"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_mail_account_singleton"),
    )

    address: Mapped[str | None]
    smtp_host: Mapped[str | None]
    smtp_port: Mapped[int | None]
    password_encrypted: Mapped[str | None]


class LlmConfig(IdMixin, UpdatedAtMixin, Base):
    """OpenAI-compatible LLM endpoint config. Two rows: kind=chat, kind=embed."""

    __tablename__ = "llm_config"
    __table_args__ = (
        UniqueConstraint("kind", name="uq_llm_config_kind"),
    )

    kind: Mapped[LlmConfigKind] = mapped_column(
        enum_column(LlmConfigKind, "llm_config_kind"),
    )
    base_url: Mapped[str | None]
    api_key_encrypted: Mapped[str | None]
    model: Mapped[str | None]


class AppSetting(UpdatedAtMixin, Base):
    """Generic key-value runtime tunables. Plaintext values only."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(primary_key=True)
    value: Mapped[str | None]
