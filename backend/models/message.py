"""Таблица переписки с HR."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import expression

from backend.models.base import Base, IdMixin


class Message(IdMixin, Base):
    __tablename__ = "message"
    # Поиск по вакансии горячий: список переписки, карточка HR и снос вакансии
    # ходят по нему на каждое действие в окне, а своих индексов на внешние
    # ключи SQLite не заводит.
    __table_args__ = (
        UniqueConstraint(
            "hr_id",
            "tg_message_id",
            "is_incoming",
            name="uq_message_hr_tgid_dir",
        ),
        # По `hr_id` поиск идёт левым началом уникальности выше; свой индекс
        # на ту же колонку нового пути не давал.
        Index("ix_message_vacancy_id", "vacancy_id"),
    )

    is_incoming: Mapped[bool] = mapped_column(server_default=expression.false())
    hr_id: Mapped[int | None] = mapped_column(ForeignKey("hr.id"))
    vacancy_id: Mapped[int | None] = mapped_column(ForeignKey("vacancy.id"))
    text: Mapped[str]
    # BigInteger — см. TelegramChannel.last_processed_msg_id: номер письма в
    # Telegram выходит за 2^31 у долгоживущих учётных записей.
    tg_message_id: Mapped[int | None] = mapped_column(BigInteger)
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
