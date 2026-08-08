"""Хранение переписки с HR."""

from datetime import datetime

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Message

async def save_incoming_message(
    session: AsyncSession,
    hr_id: int,
    vacancy_id: int | None,
    text: str,
    tg_message_id: int,
    received_at: datetime,
    *,
    media_kind: str | None = None,
    media_path: str | None = None,
    media_name: str | None = None,
) -> Message:
    new_msg = Message(
        is_incoming=True,
        hr_id=hr_id,
        vacancy_id=vacancy_id,
        text=text,
        tg_message_id=tg_message_id,
        sent_at=received_at,
        media_kind=media_kind,
        media_path=media_path,
        media_name=media_name,
    )
    session.add(new_msg)
    await session.flush()
    return new_msg


async def list_messages_for_hr(
    session: AsyncSession,
    hr_id: int,
    *,
    limit: int = 50,
    before_id: int | None = None,
    before_sent_at: datetime | None = None,
) -> tuple[list[Message], bool]:
    """A page of messages for an HR, oldest-first (chat-render order).

    Fetches the newest ``limit`` messages strictly older than the cursor
    ``(before_sent_at, before_id)`` (or the tail of the chat if both are
    None), ordered ``sent_at DESC, id DESC`` then reversed to oldest-first.
    Returns ``(messages, has_more)`` so the UI knows whether to keep
    offering "load older".

    Cursor пагинация по составной паре `(sent_at, id)` — НЕ по чистому
    `id`. Catch-up бэкаппит исторические DM-ы офлайн-периода после ингеста
    свежих realtime-сообщений: id у "более старого по времени" ряда может
    оказаться выше, чем у уже отображённого. Чистая пагинация по
    `id < before_id` тогда либо пропускает ряды, либо возвращает дубли.
    Composite-cursor устраняет это.
    """
    q = select(Message).where(Message.hr_id == hr_id)
    if before_sent_at is not None and before_id is not None:
        # SQL row-value: (sent_at, id) < (before_sent_at, before_id).
        # SQLite поддерживает row-value сравнения с 3.15+ — у нас новее,
        # но на всякий случай пишем эквивалентный OR-вариант, чтобы не
        # привязываться к конкретной реализации row-value.
        q = q.where(
            or_(
                Message.sent_at < before_sent_at,
                and_(
                    Message.sent_at == before_sent_at,
                    Message.id < before_id,
                ),
            )
        )
    elif before_id is not None:
        # Backwards-compat для старых клиентов, не присылающих
        # before_sent_at: оставляем прежнее поведение.
        q = q.where(Message.id < before_id)
    rows = (
        await session.scalars(
            q.order_by(Message.sent_at.desc(), Message.id.desc())
            .limit(limit + 1)
        )
    ).all()
    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]
    return list(reversed(rows)), has_more


async def count_unread_incoming(session: AsyncSession) -> int:
    """Count incoming HR messages whose read_at is still NULL.

    Excludes tombstones — a deleted incoming row that was never read
    would otherwise inflate the badge with no way to clear it from the UI.
    ``updates.on_dm_delete`` also seals ``read_at`` defensively, but the filter
    here protects against any future code that flips ``is_deleted`` only.
    """
    n = await session.scalar(
        select(func.count(Message.id)).where(
            Message.is_incoming,
            Message.read_at.is_(None),
            Message.is_deleted.is_(False),
        )
    )
    return int(n or 0)
