"""Хранение переписки с HR."""

from datetime import datetime, timezone

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Message
from backend.payloads import IncomingMessage, OutgoingMessage
from backend.repository.paging import trim_page

# Раскрывается звёздочкой в `.where(...)`: `.where(*UNREAD_INCOMING, ...)`.
# Надгробие исключено намеренно — удалённое, но не прочитанное входящее иначе
# раздувает счётчик, и погасить его из окна нечем.
UNREAD_INCOMING = (
    Message.is_incoming,
    Message.read_at.is_(None),
    Message.is_deleted.is_(False),
)


async def save_incoming_message(
    session: AsyncSession, incoming: IncomingMessage
) -> Message:
    """Положить письмо HR в переписку.

    Письмо приходит свёрткой, а не россыпью доводов: восемь значений здесь —
    одно письмо, и порознь ни одно из них строку не составляет. Зеркально
    исходящему (`save_outgoing_message`), у которого свёртка была с самого
    начала.
    """
    new_msg = Message(
        is_incoming=True,
        hr_id=incoming.hr_id,
        vacancy_id=incoming.vacancy_id,
        text=incoming.text,
        tg_message_id=incoming.tg_message_id,
        sent_at=incoming.received_at,
        media_kind=incoming.media_kind,
        media_path=incoming.media_path,
        media_name=incoming.media_name,
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


async def mark_outgoing_read(
    session: AsyncSession, hr_id: int, up_to_tg_id: int, now: datetime
) -> int:
    """Пометить прочитанными наши письма этому HR до названного номера.

    Telegram сообщает о прочтении не строкой, а границей: «всё до этого
    номера прочитано». Строки без номера в границу не попадают вовсе — они
    писались под замком отправки, и в Telegram их не существует.

    Живёт рядом с отметкой входящих нарочно: что значит «прочитано», у обеих
    сторон переписки одно, а писал это прежде обработчик события своим
    запросом.

    Транзакцию закрывает зовущий.
    """
    done = await session.execute(
        update(Message)
        .where(
            Message.hr_id == hr_id,
            Message.is_incoming.is_(False),
            Message.tg_message_id.is_not(None),
            Message.tg_message_id <= up_to_tg_id,
            Message.read_at.is_(None),
        )
        .values(read_at=now)
    )
    return done.rowcount or 0


async def overwrite_message_text(
    session: AsyncSession,
    hr_id: int,
    tg_message_id: int,
    *,
    is_incoming: bool,
    text: str,
) -> int:
    """Переписать текст сохранённой строки, пометив её изменённой; сколько вышло.

    Направление приходит доводом, а не вычисляется здесь: номера сообщений
    в Telegram свои у каждой переписки, и во входящих вполне может лежать
    строка с тем же номером, что и в исходящих. Чья правка пришла, решает
    обработчик — по отправителю и признаку «своё».

    Пометка — не украшение: без неё пользователь читал бы новую редакцию,
    считая её исходной.

    **Доводов пять, и свёртке они не подлежат.** Три из них — адрес строки,
    и группа тут настоящая, но потребитель у неё один: объявление под неё
    завелось бы раньше второго. Отбор доводом (как у `tombstone_messages`)
    не годится по обратной причине: там зовущих трое и отборы у них разные,
    здесь зовущий один и отбор у него неизменен.

    Транзакцию закрывает зовущий.
    """
    done = await session.execute(
        update(Message)
        .where(
            Message.hr_id == hr_id,
            Message.tg_message_id == tg_message_id,
            Message.is_incoming.is_(is_incoming),
        )
        .values(text=text, is_edited=True)
    )
    return done.rowcount or 0


async def hr_ids_of_live_messages(session: AsyncSession, *where) -> set[int]:
    """Чьи это строки: номера HR у живых строк из отбора.

    Отбор доводом здесь по той же причине, что у `tombstone_messages`, с
    которым это объявление ходит в паре: спрашивают ровно затем, чтобы
    решить, чьё окно будить после похорон, а отбор у похорон приходит от
    зовущего — то пачкой номеров по чату, то россыпью без чата.

    Оговорку «уже похороненное не в счёт» объявление держит само: переписку,
    в которой ничего не изменилось, перерисовывать незачем. Спрашивать при
    этом надо до похорон — после них те же строки из отбора выпадут.
    """
    rows = await session.execute(
        select(Message.hr_id).where(
            *where,
            Message.hr_id.is_not(None),
            Message.is_deleted.is_(False),
        )
    )
    return {hr_id for (hr_id,) in rows}


async def newest_tg_message_id(session: AsyncSession, hr_id: int) -> int:
    """Наибольший номер Telegram, что у нас есть по этому человеку, или ноль.

    Отметка снимается перед догоном и участвует в потолке сверки удалённого:
    хоронится то, что не выше наибольшего из этой отметки и номеров, пришедших
    в ответе Telegram. Всё, что появилось выше потолка, пришло уже во время
    прохода, а значит отсутствует в ответе не потому, что стёрто. Своя роль у
    отметки одна: не дать похоронам обойти стёртое последнее письмо, которого
    в ответе уже нет.

    Обе стороны переписки, а не одни входящие: удаляют и своё.
    """
    newest = (
        await session.scalars(
            select(func.max(Message.tg_message_id)).where(Message.hr_id == hr_id)
        )
    ).first()
    return newest or 0


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
        .where(*where, *UNREAD_INCOMING)
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
        vacancy_id=out.vacancy_id,
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


def _older_than(q, before_id: int | None, before_sent_at: datetime | None):
    """Отсечь страницу по составной метке «время и номер».

    Пагинация идёт по паре `(sent_at, id)`, а НЕ по чистому `id`. Догон
    заливает исторические письма офлайн-периода уже после свежих: у более
    старого по времени письма номер может оказаться больше, чем у
    показанного. Отсечка по одному номеру тогда либо пропускает письма,
    либо возвращает их дважды.

    Пара сравнивается развёрнутым `ИЛИ`, а не построчным сравнением: SQLite
    его понимает с 3.15, но привязываться к этому незачем. Половина метки
    отсечкой не считается: окно шлёт обе или ни одной, а одинокий номер и
    есть та самая отсечка, что пропускает письма.
    """
    if before_sent_at is None or before_id is None:
        return q
    return q.where(
        or_(
            Message.sent_at < before_sent_at,
            and_(
                Message.sent_at == before_sent_at,
                Message.id < before_id,
            ),
        )
    )


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

    **Доводов пять, и свёртке они не подлежат.** Указатель из времени и
    номера — настоящая пара, но потребитель у неё один: объявление под
    указатель завелось бы раньше второго. Отсечка страницы —
    :func:`_older_than`, и обе половины указателя нужны ей вместе.
    """
    q = _older_than(
        select(Message).where(Message.hr_id == hr_id), before_id, before_sent_at
    )
    rows = (
        await session.scalars(
            q.order_by(Message.sent_at.desc(), Message.id.desc())
            .limit(limit + 1)
        )
    ).all()
    page, has_more = trim_page(list(rows), limit)
    return list(reversed(page)), has_more


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
