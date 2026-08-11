"""Хранение переписки с HR."""

from datetime import datetime, timezone

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Message
from backend.payloads import OutgoingMessage

# Раскрывается звёздочкой в `.where(...)`: `.where(*UNREAD_INCOMING, ...)`.
# Надгробие исключено намеренно — удалённое, но не прочитанное входящее иначе
# раздувает счётчик, и погасить его из окна нечем.
UNREAD_INCOMING = (
    Message.is_incoming,
    Message.read_at.is_(None),
    Message.is_deleted.is_(False),
)


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


async def mark_incoming_read(
    session: AsyncSession, hr_id: int, now: datetime
) -> int:
    """Пометить прочитанными все входящие от этого HR; сколько пометили.

    Надгробия гасятся наравне с живыми строками, и поэтому условие здесь
    своё, а не `UNREAD_INCOMING`: у того есть третья часть «не надгробие».
    Счётчик непрочитанного надгробий и так не считает, так что это
    подстраховка — на случай, если строку похоронит кто-то мимо
    `tombstone_messages`, который гасит их сам.

    Транзакцию закрывает зовущий.
    """
    done = await session.execute(
        update(Message)
        .where(
            Message.hr_id == hr_id,
            Message.is_incoming,
            Message.read_at.is_(None),
        )
        .values(read_at=now)
    )
    return done.rowcount or 0


async def tombstone_messages(session: AsyncSession, *where) -> int:
    """Поставить надгробия отобранным строкам; сколько поставили.

    Отбор — дело зовущего: удаление приходит то пачкой номеров по чату, то
    россыпью без чата, то вычисляется догоном как «в нашей переписке есть, а
    в ответе Telegram нет». Общее у всех троих — что значит «удалено».

    Уже надгробия из отбора выпадают, и это не бережливость: одну и ту же
    строку накрывают оба пути — оповещение об удалении и догон переписки,
    вычисляющий удалённое сам, — а зовущие по числу задетых строк решают,
    будить ли окно. Второй по счёту не должен перерисовывать переписку, в
    которой ничего не изменилось.

    Непрочитанное входящее заодно гасится. Счётчики непрочитанного надгробий
    и так не считают, так что это подстраховка — на случай, если строку
    похоронит кто-то мимо этого объявления. Запроса поэтому два — исходящим
    время прочтения не ставится вовсе, — и время ставится первым: после
    надгробий эти же строки из отбора выпадут.

    Транзакцию закрывает зовущий.
    """
    alive = (*where, Message.is_deleted.is_(False))
    await session.execute(
        update(Message)
        .where(*alive, Message.is_incoming, Message.read_at.is_(None))
        .values(read_at=datetime.now(timezone.utc))
    )
    buried = await session.execute(
        update(Message).where(*alive).values(is_deleted=True)
    )
    return buried.rowcount or 0


async def find_outgoing_message(
    session: AsyncSession, hr_id: int, tg_message_id: int
) -> Message | None:
    """Наше исходящее с этим номером, если оно уже записано.

    Чем опознаётся наша исходящая, сказано здесь один раз: то же условие
    держит уникальность, по которой ловится гонка.
    """
    return (
        await session.scalars(
            select(Message).where(
                Message.hr_id == hr_id,
                Message.tg_message_id == tg_message_id,
                Message.is_incoming.is_(False),
            )
        )
    ).first()


async def save_outgoing_message(
    session: AsyncSession, out: OutgoingMessage
) -> tuple[Message, bool]:
    """Записать наше исходящее; отдать строку и «записали впервые».

    Повтор — штатный случай, а не сбой: одно письмо приходит и от нас, и
    эхом из Telegram, и кто из двоих успел первым, заранее не известно.
    Ловится он уникальностью `(hr_id, tg_message_id, is_incoming)`, и
    проигравший гонку получает уже лежащую строку, а не отказ.

    На повторе сессия откатывается: другой незакрытой работы в этой
    транзакции быть не должно.
    """
    row = Message(
        is_incoming=False,
        hr_id=out.hr_id,
        text=out.text,
        tg_message_id=out.tg_message_id,
        sent_at=out.sent_at,
        media_kind=out.media_kind,
        media_path=out.media_path,
        media_name=out.media_name,
    )
    session.add(row)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        stored = await find_outgoing_message(
            session, out.hr_id, out.tg_message_id
        )
        if stored is None:
            raise
        return stored, False
    return row, True


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

    ``tombstone_messages`` also seals ``read_at`` defensively, but the
    tombstone filter inside ``UNREAD_INCOMING`` covers any future code that
    flips ``is_deleted`` alone.
    """
    n = await session.scalar(
        select(func.count(Message.id)).where(*UNREAD_INCOMING)
    )
    return int(n or 0)
