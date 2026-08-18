"""Обработчики оповещений Telegram: входящее, эхо, правка, удаление, отметка о прочтении.

Здесь только опознание события и зов того, кто умеет с ним работать: сама
работа — чтение и запись в базу — живёт в конвейере (`flows/dm`, `flows/dm_sync`).
Обработчик отстреливает на каждое событие сервера, и держать в нём сессии
значило бы, что о внутренностях бота знает ещё и слой оповещений.
"""

import logging

# На верхнем уровне, чтобы обработчик оповещений не платил поиском по
# ``sys.modules`` на каждое событие сервера.
from pyrogram.raw.types import PeerUser as _PeerUser
from pyrogram.raw.types import UpdateReadHistoryOutbox as _UpdateReadHistoryOutbox

from backend.flows import dm_sync
from backend.flows.dm import process_dm
from backend.message_text import extract_text
from backend.models import BotMode
from backend.repository.hr_identify import find_known_hr

from backend.notify import fire

logger = logging.getLogger(__name__)


async def _muted(bot) -> bool:
    """Молчит ли бот сейчас — один вопрос на все пять обработчиков.

    Выключенный не читает ничего: ни писем, ни правок, ни удалений, ни
    отметок о прочтении. Спрашивают его первой строкой все пятеро, и разойдись
    они, одна дорога продолжала бы писать в базу у выключенного бота.
    """
    return (await bot._current_mode()) is BotMode.OFF


async def on_raw_update(bot, _client, update, _users, _chats) -> None:
    """Отметка о прочтении наших писем; всё остальное пропускается.

    Дешёвый отсев идёт первым: сырые оповещения отстреливают на каждое событие
    сервера, и опознание должно стоить дешевле проверки режима.
    """
    if not isinstance(update, _UpdateReadHistoryOutbox):
        return
    peer = getattr(update, "peer", None)
    if not isinstance(peer, _PeerUser):
        return
    if await _muted(bot):
        return
    hr_id = await dm_sync.mark_read(
        bot._session_factory, peer.user_id, update.max_id
    )
    if hr_id is not None:
        fire(bot.on_hr_read, "on_hr_read", hr_id, update.max_id)


async def on_dm_edit(bot, _client, msg) -> None:
    """Правка письма на стороне Telegram."""
    if await _muted(bot):
        return
    if not msg.chat:
        return
    synced = await dm_sync.sync_edit(bot._session_factory, msg)
    if synced is None:
        return
    hr_id, is_incoming = synced
    # Правленое чужое письмо может ещё сидеть в копилке отложенного разбора —
    # HR успевает поправить его в первую минуту, — и разбирать надо свежее.
    if is_incoming:
        bot._ingestion.update_dm_buffer_text(hr_id, msg.id, extract_text(msg))
    logger.debug(
        "DM edit synced: hr=%d tg_msg=%d incoming=%s", hr_id, msg.id, is_incoming
    )
    fire(bot.on_new_message, "on_new_message", hr_id)


async def on_dm_delete(bot, _client, messages) -> None:
    """Удаление писем на стороне Telegram."""
    if await _muted(bot):
        return
    touched = await dm_sync.tombstone_deleted(
        bot._session_factory, messages, bot._ingestion.remove_dm_buffer_msg
    )
    for hr_id in touched:
        fire(bot.on_new_message, "on_new_message", hr_id)


async def on_dm_outgoing(bot, _client, msg) -> None:
    """Письмо, набранное человеком из другого клиента Telegram.

    Молчит вместе с входящими: выключенный бот не читает переписку ни в одну
    сторону.
    """
    if await _muted(bot):
        return
    if not msg.chat:
        return
    hr_id = await dm_sync.store_outgoing(bot._session_factory, bot._client, msg)
    if hr_id is not None:
        fire(bot.on_new_message, "on_new_message", hr_id)


async def on_dm(bot, _client, msg) -> None:
    # Off mode silences everything, including reading HR replies.
    if await _muted(bot):
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
