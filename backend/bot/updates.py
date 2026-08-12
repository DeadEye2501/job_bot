"""Обработчики оповещений Telegram: входящее, эхо, правка, удаление, отметка о прочтении."""

import logging

# На верхнем уровне, чтобы обработчик оповещений не платил поиском по
# ``sys.modules`` на каждое событие сервера.
from pyrogram.raw.types import PeerUser as _PeerUser
from pyrogram.raw.types import UpdateReadHistoryOutbox as _UpdateReadHistoryOutbox

from backend.flows.dm import persist_outgoing_dm, process_dm
from backend.helpers import extract_dm_text
from backend.helpers import extract_text
from backend.models import BotMode
from backend.models import Message
from backend.repository.hr_identify import find_known_hr
from backend.repository.messages import (
    hr_ids_of_live_messages,
    mark_outgoing_read,
    overwrite_message_text,
    tombstone_messages,
)

from backend.notify import fire

logger = logging.getLogger(__name__)


async def on_raw_update(bot, _client, update, _users, _chats) -> None:
    """Catch ``UpdateReadHistoryOutbox`` to mark our outgoing rows as
    read by the HR. Everything else is ignored — raw updates fire on
    every server event so the cheap-out has to come first.
    """
    if not isinstance(update, _UpdateReadHistoryOutbox):
        return
    peer = getattr(update, "peer", None)
    if not isinstance(peer, _PeerUser):
        return
    if (await bot._current_mode()) is BotMode.OFF:
        return
    from datetime import datetime as _dt, timezone as _tz

    user_id = peer.user_id
    max_id = update.max_id
    now = _dt.now(_tz.utc)
    async with bot._session_factory() as session:
        hr = await find_known_hr(session, user_id, None)
        if hr is None:
            return
        updated = await mark_outgoing_read(session, hr.id, max_id, now)
        await session.commit()
        hr_id = hr.id
    if updated:
        fire(bot.on_hr_read, "on_hr_read", hr_id, max_id)


async def on_dm_edit(bot, _client, msg) -> None:
    """Sync Telegram edits — overwrite text + mark is_edited=True."""
    if (await bot._current_mode()) is BotMode.OFF:
        return
    if not msg.chat:
        return
    chat_id = msg.chat.id
    chat_username = getattr(msg.chat, "username", None)
    is_incoming = bool(getattr(msg, "from_user", None)
                       and not getattr(msg, "outgoing", False))
    async with bot._session_factory() as session:
        hr = await find_known_hr(session, chat_id, chat_username)
        if hr is None:
            return
        updated = await overwrite_message_text(
            session,
            hr.id,
            msg.id,
            is_incoming=is_incoming,
            text=extract_dm_text(msg),
        )
        await session.commit()
        hr_id = hr.id
    # Если это сообщение всё ещё сидит в debounce-буфере (HR отредак-
    # тировал в первые 60 сек) — обновим текст там тоже, чтобы
    # классификатор видел свежее содержимое.
    if updated and is_incoming:
        bot._ingestion.update_dm_buffer_text(hr_id, msg.id, extract_text(msg))
    if updated:
        logger.debug(
            "DM edit synced: hr=%d tg_msg=%d incoming=%s",
            hr_id, msg.id, is_incoming,
        )
    if updated:
        fire(bot.on_new_message, "on_new_message", hr_id)


async def on_dm_delete(bot, _client, messages) -> None:
    """Sync Telegram deletes — set is_deleted=True, keep the row.

    Pyrogram delete updates are sparse: ``m.chat`` is often ``None`` for
    secret-chat / channel-less tombstones, and only ``m.id`` is
    guaranteed. We group by chat when we have it; otherwise fall back to
    a chatless sweep restricted to incoming rows. ``tg_message_id`` is
    per-chat in Telegram (NOT globally unique — two HRs routinely share
    early ids 1, 2, 3...), so the chatless branch could in principle
    flip an unrelated HR's row. We narrow to incoming because chatless
    deletes practically only happen for secret/channel sources we don't
    store anyway, and incoming-only further shrinks the collision window.
    Outgoing tombstones missed here will be reconciled the next time we
    load the chat from Telegram on app restart.

    Что значит «удалено» — надгробие, гашение непрочитанного входящего и
    оговорка «уже похороненное не трогаем» — объявлено один раз в
    ``repository.messages.tombstone_messages``; здесь остаётся только отбор.
    """
    if (await bot._current_mode()) is BotMode.OFF:
        return
    with_chat: dict[int, list[int]] = {}
    chatless_ids: list[int] = []
    for m in messages:
        chat = getattr(m, "chat", None)
        chat_id = getattr(chat, "id", None) if chat else getattr(m, "chat_id", None)
        if chat_id is None:
            chatless_ids.append(m.id)
        else:
            with_chat.setdefault(chat_id, []).append(m.id)
    if not with_chat and not chatless_ids:
        return

    touched_hr_ids: set[int] = set()

    for chat_id, msg_ids in with_chat.items():
        async with bot._session_factory() as session:
            # Resolve HR by chat_id; for username-only HRs we need the
            # username fallback that Pyrogram supplies on chat objects.
            chat_username = None
            for m in messages:
                chat = getattr(m, "chat", None)
                if chat and getattr(chat, "id", None) == chat_id:
                    chat_username = getattr(chat, "username", None)
                    break
            hr = await find_known_hr(session, chat_id, chat_username)
            if hr is None:
                continue
            rowcount = await tombstone_messages(
                session,
                Message.hr_id == hr.id,
                Message.tg_message_id.in_(msg_ids),
            )
            await session.commit()
            if rowcount:
                touched_hr_ids.add(hr.id)
                # Если удалённое сообщение всё ещё сидит в debounce-буфере
                # — выкинем его оттуда, чтобы не учитывать в классификации.
                #
                # Счётчик считает только живые строки, поэтому сообщение,
                # похороненное другим путём, пока оно лежало в буфере, из
                # буфера не выпадет. Разводить этот случай с «строк не
                # нашлось вовсе» — где буфер трогать нельзя — можно только
                # вторым запросом, и он этого не стоит.
                for tg_msg_id in msg_ids:
                    bot._ingestion.remove_dm_buffer_msg(hr.id, tg_msg_id)

    if chatless_ids:
        async with bot._session_factory() as session:
            # Chatless sweep — narrowed to incoming so we never flip an
            # outgoing row that happens to share a tg_message_id with a
            # delete from a different HR.
            # Спрашиваем до похорон и тем же отбором: иначе в смешанной пачке
            # уже похороненная строка чужого HR разбудила бы окно за переписку,
            # в которой ничего не изменилось.
            chatless = (
                Message.tg_message_id.in_(chatless_ids),
                Message.is_incoming,
            )
            hr_ids = await hr_ids_of_live_messages(session, *chatless)
            rowcount = await tombstone_messages(session, *chatless)
            await session.commit()
            if rowcount:
                touched_hr_ids |= hr_ids

    if touched_hr_ids:
        logger.info(
            "DM tombstoned across %d hr(s)",
            len(touched_hr_ids),
        )
    for hr_id in touched_hr_ids:
        fire(bot.on_new_message, "on_new_message", hr_id)


async def on_dm_outgoing(bot, _client, msg) -> None:
    """Capture messages the user typed from another TG client (phone /
    desktop) so the in-app chat stays in sync. Mirrors the OFF-mode
    gating of the incoming handler — OFF silences both directions.

    Resolves HR by recipient's user_id (msg.chat.id for private chats).
    Записью и отсевом повторов заведует `persist_outgoing_dm`, общий с
    догоном переписки; здесь остаётся опознание собеседника и решение,
    будить ли окно.
    """
    if (await bot._current_mode()) is BotMode.OFF:
        return
    if not msg.chat:
        return

    recipient_id = msg.chat.id
    recipient_username = getattr(msg.chat, "username", None)
    async with bot._session_factory() as session:
        hr = await find_known_hr(session, recipient_id, recipient_username)
        if hr is None:
            return
        hr_id = hr.id
    outcome = await persist_outgoing_dm(bot._session_factory, bot._client, msg, hr_id)
    # Уже лежащая строка — это эхо нашей же отправки: писать нечего, а вот
    # окно ещё не знает и должно обновиться синхронно с прилётом эха.
    # Несостоявшаяся запись — другое дело: там либо гонка, и оповестит тот,
    # кто выиграл, либо беда, и оповещать не о чем.
    if outcome == "not_stored":
        return
    fire(bot.on_new_message, "on_new_message", hr_id)


async def on_dm(bot, _client, msg) -> None:
    # Off mode silences everything, including reading HR replies.
    if (await bot._current_mode()) is BotMode.OFF:
        return
    await process_dm(
        msg,
        bot._lm_client,
        bot._lm_chat_model,
        bot._session_factory,
        client=bot._client,
        schedule_classification=bot._ingestion.schedule_dm_classification,
    )
    # `on_vacancies_changed` НЕ пушим здесь — статус вакансии флипнется
    # debounce-таском через ~60с после burst'а (см. flows/dm_classify.py,
    # _run_debounced_classify), он же сам пушнёт сигнал. До того статус
    # не менялся, любой ранний refetch вкладки «Вакансии» отдал бы
    # тот же набор статусов и зря грузил бы БД/UI.
    # Push a UI signal so an open Contacts/HR chat with this HR can
    # refresh in real time without polling. We look up hr_id after
    # process_dm rather than threading a callback through it — keeps
    # process_dm's signature clean and avoids touching unrelated flows.
    # Пустой обработчик отсеивается и здесь, хотя `fire` умеет это сам:
    # без окна не нужен и поиск HR в базе, который идёт следом.
    if bot.on_new_message is None:
        return
    if not msg.from_user:
        return
    try:
        async with bot._session_factory() as session:
            hr = await find_known_hr(
                session,
                msg.from_user.id,
                msg.from_user.username,
            )
        if hr is not None:
            fire(bot.on_new_message, "on_new_message", hr.id)
    except Exception:
        # Поломку самого оповещения глотает `fire`; сюда долетает только
        # сбой поиска HR, то есть обращение к базе.
        logger.exception("echo lookup for the window failed")
