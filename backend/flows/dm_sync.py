"""Сверка переписки с тем, что случилось с ней на стороне Telegram.

Письмо не только приходит: его правят, удаляют и прочитывают, и обо всём этом
Telegram присылает оповещение. Приход письма разбирает `flows/dm`, остальные
три случая — здесь; общее у них то, что менять надо уже лежащую строку.

Живёт отдельно от обработчиков (`bot/updates`) потому, что обработчик события
не ходит в базу и ничего не вычисляет — он опознаёт событие и зовёт того, кто
это умеет. Прежде тела трёх обработчиков лежали прямо в них, и вместе с
работой туда переехало знание о внутренностях бота.

Наружу каждый зов отдаёт того, кого задел: будить окно — дело зовущего, у него
для этого крючок.
"""

import logging

from backend.flows.dm import persist_outgoing_dm
from backend.message_text import extract_dm_text
from backend.models import Message
from backend.repository.hr_identify import find_known_hr
from backend.repository.messages import (
    hr_ids_of_live_messages,
    mark_outgoing_read,
    overwrite_message_text,
    tombstone_messages,
)
from backend.telegram_time import utc_now

logger = logging.getLogger(__name__)


async def mark_read(session_factory, user_id: int, max_id: int) -> int | None:
    """Отметить наши письма прочитанными; отдать человека, если что-то легло.

    Пусто значит «будить окно не о чем»: собеседник неизвестен или все письма
    до названного номера уже были отмечены.
    """
    async with session_factory() as session:
        hr = await find_known_hr(session, user_id, None)
        if hr is None:
            return None
        updated = await mark_outgoing_read(
            session, hr.id, max_id, utc_now()
        )
        await session.commit()
        return hr.id if updated else None


async def sync_edit(session_factory, msg) -> tuple[int, bool] | None:
    """Переписать текст правленого письма; отдать человека и сторону письма.

    Сторона нужна зовущему: правку своего письма разбор не касается, а
    правленое чужое может ещё сидеть в копилке отложенного разбора.
    """
    chat_username = getattr(msg.chat, "username", None)
    is_incoming = bool(
        getattr(msg, "from_user", None) and not getattr(msg, "outgoing", False)
    )
    async with session_factory() as session:
        hr = await find_known_hr(session, msg.chat.id, chat_username)
        if hr is None:
            return None
        updated = await overwrite_message_text(
            session,
            hr.id,
            msg.id,
            is_incoming=is_incoming,
            text=extract_dm_text(msg),
        )
        await session.commit()
        return (hr.id, is_incoming) if updated else None


def _split_by_chat(messages) -> tuple[dict[int, list[int]], list[int]]:
    """Разложить надгробия по перепискам; безадресные — отдельным списком.

    Оповещения об удалении приходят скупыми: переписки у них часто нет вовсе,
    и надёжен только номер письма. Известные группируются по переписке,
    остальные уходят в сплошной проход (см. :func:`_tombstone_chatless`).
    """
    with_chat: dict[int, list[int]] = {}
    chatless_ids: list[int] = []
    for m in messages:
        chat = getattr(m, "chat", None)
        chat_id = getattr(chat, "id", None) if chat else getattr(m, "chat_id", None)
        if chat_id is None:
            chatless_ids.append(m.id)
        else:
            with_chat.setdefault(chat_id, []).append(m.id)
    return with_chat, chatless_ids


def _chat_username(messages, chat_id: int) -> str | None:
    """Ник переписки из пачки надгробий.

    Нужен затем, что человек мог быть заведён по одному нику, без числового
    идентификатора, — по нему его и найдут.
    """
    for m in messages:
        chat = getattr(m, "chat", None)
        if chat and getattr(chat, "id", None) == chat_id:
            return getattr(chat, "username", None)
    return None


async def _tombstone_in_chat(
    session_factory, chat_id: int, msg_ids: list[int], messages
):
    """Похоронить письма одной переписки; отдать человека, если что-то легло."""
    async with session_factory() as session:
        hr = await find_known_hr(session, chat_id, _chat_username(messages, chat_id))
        if hr is None:
            return None
        rowcount = await tombstone_messages(
            session,
            Message.hr_id == hr.id,
            Message.tg_message_id.in_(msg_ids),
        )
        await session.commit()
        return hr.id if rowcount else None


async def _tombstone_chatless(session_factory, chatless_ids: list[int]) -> set[int]:
    """Похоронить безадресные надгробия; отдать задетых людей.

    Номера писем у пользовательской учётной записи общие на все личные
    переписки, а не свои у каждой, — попадание по одному номеру поэтому
    точное, чужую строку такой проход не заденет. Направление письма в отбор
    не входит: наше стёртое надо хоронить тем же оповещением, а жди оно
    догона переписки — глубже его предела не похоронилось бы никогда.

    Спрашиваем до похорон и тем же отбором: иначе в смешанной пачке уже
    похороненная строка чужого человека разбудила бы окно за переписку, в
    которой ничего не изменилось.
    """
    async with session_factory() as session:
        chatless = (Message.tg_message_id.in_(chatless_ids),)
        hr_ids = await hr_ids_of_live_messages(session, *chatless)
        rowcount = await tombstone_messages(session, *chatless)
        await session.commit()
    return hr_ids if rowcount else set()


def _forget_all(forget_pending, hr_id: int, msg_ids) -> None:
    """Выбросить названные письма из копилки отложенного разбора у человека."""
    for tg_msg_id in msg_ids:
        forget_pending(hr_id, tg_msg_id)


async def tombstone_deleted(session_factory, messages, forget_pending) -> set[int]:
    """Похоронить удалённые письма; отдать задетых людей.

    Похороненное письмо выкидывается из копилки отложенного разбора, чтобы не
    попасть в классификацию, — это и делает `forget_pending`. Счётчик при этом
    считает только живые строки, поэтому письмо, похороненное другим путём,
    пока оно лежало в копилке, из неё не выпадет; разводить этот случай с
    «строк не нашлось вовсе» можно только вторым запросом, и он этого не стоит.
    """
    with_chat, chatless_ids = _split_by_chat(messages)
    if not with_chat and not chatless_ids:
        return set()

    touched: set[int] = set()
    for chat_id, msg_ids in with_chat.items():
        hr_id = await _tombstone_in_chat(session_factory, chat_id, msg_ids, messages)
        if hr_id is None:
            continue
        touched.add(hr_id)
        _forget_all(forget_pending, hr_id, msg_ids)
    if chatless_ids:
        chatless_hrs = await _tombstone_chatless(session_factory, chatless_ids)
        touched |= chatless_hrs
        for hr_id in chatless_hrs:
            _forget_all(forget_pending, hr_id, chatless_ids)
    if touched:
        logger.info("DM tombstoned across %d hr(s)", len(touched))
    return touched


async def store_outgoing(session_factory, client, msg) -> int | None:
    """Записать письмо, набранное из другого клиента; отдать человека.

    Пусто значит «будить окно не о чем». Уже лежащая строка исключение: это
    эхо нашей же отправки, писать нечего, а окно ещё не знает и должно
    обновиться синхронно с прилётом эха — поэтому человек отдаётся и тогда.
    Несостоявшаяся запись — другое дело: там либо гонка, и оповестит тот, кто
    выиграл, либо беда, и оповещать не о чем.
    """
    recipient_username = getattr(msg.chat, "username", None)
    async with session_factory() as session:
        hr = await find_known_hr(session, msg.chat.id, recipient_username)
        if hr is None:
            return None
        hr_id = hr.id
    outcome = await persist_outgoing_dm(session_factory, client, msg, hr_id)
    return None if outcome == "not_stored" else hr_id
