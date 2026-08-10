"""Догон пропущенной переписки с HR."""

import logging
import asyncio

from sqlalchemy import select

from backend.bot.media import classify_media, download_media
from backend.flows.dm import process_dm
from backend.helpers import extract_dm_text, telegram_peer
from backend.payloads import OutgoingMessage
from backend.repository.hr_list import list_hrs_for_backfill
from backend.repository.messages import save_outgoing_message

logger = logging.getLogger(__name__)


# DM catch-up batching: ``BATCH_SIZE`` HR'ов параллельно через
# ``asyncio.gather``, потом ``BATCH_DELAY_SEC`` пауза перед следующим
# батчем — чтобы TG-rate-limit window успевал сбрасываться. Параметры
# подобраны под flood_sleep_threshold=60 в adapters/telegram.py: даже
# если внутри батча словим короткий FloodWait, Pyrogram съест его сам.
_DM_CATCHUP_BATCH_SIZE = 20


_DM_CATCHUP_BATCH_DELAY_SEC = 1.0


async def backfill_hr_dm_history(
    client,
    hr,
    lm_client,
    lm_chat_model,
    session_factory,
    *,
    backfill_limit: int,
    on_message_persisted=None,
    on_vacancies_changed=None,
    schedule_classification=None,
) -> None:
    """Pull the DM history of one HR and persist it.

    Used by ``catch_up_missed_dms`` (per-HR loop) and the auto-apply path
    (when ``find_or_create_hr`` just minted a new HR — without this hook
    the chat would show only the cover-letter we just sent, prior history
    invisible until the next OFF→active transition).
    """
    from datetime import datetime, timezone
    from backend.models import Message
    from pyrogram.errors import FloodWait, PeerIdInvalid

    target = telegram_peer(hr)
    if target is None:
        return
    messages = []
    try:
        async for msg in client.get_chat_history(target, limit=backfill_limit):
            messages.append(msg)
    except PeerIdInvalid:
        # Pyrogram peer-cache не знает этого id (HR добавлен по
        # @username без предыдущего DM, либо session сброшен).
        # Пробуем resolve по username, если есть; иначе skip.
        logger.warning(
            "backfill: PeerIdInvalid для hr %d (target=%s) — пробую "
            "resolve по @username",
            hr.id, target,
        )
        if hr.telegram_username:
            try:
                await client.get_users(hr.telegram_username)
                # После get_users peer попадает в cache; повторим
                # get_chat_history.
                messages = []
                async for msg in client.get_chat_history(
                    hr.telegram_username, limit=backfill_limit
                ):
                    messages.append(msg)
            except Exception as e:
                logger.warning(
                    "backfill: resolve fallback failed для hr %d: %s",
                    hr.id, e,
                )
                return
        else:
            return
    except FloodWait as e:
        # Pyrogram не съел FloodWait сам (значит, он длиннее
        # ``sleep_threshold`` из make_client). Ждём явно ровно столько,
        # сколько просит TG, и ретраим один раз — этого достаточно для
        # типичных peak'ов rate-limit'а во время batch catch-up'а. Если
        # и второй раз FloodWait — значит, реально серьёзный штраф,
        # дальше уже скипаем HR'а до следующего OFF→active цикла.
        wait = int(getattr(e, "value", 30))
        logger.info(
            "backfill: FloodWait %ds на hr %d — жду и ретраим",
            wait, hr.id,
        )
        await asyncio.sleep(wait + 1)
        try:
            messages = []
            async for msg in client.get_chat_history(target, limit=backfill_limit):
                messages.append(msg)
        except Exception:
            logger.exception(
                "backfill: retry после FloodWait не помог hr %d", hr.id,
            )
            return
    had_new = False
    # Oldest-first so the chat order stays sane in the UI.
    for msg in reversed(messages):
        if msg.outgoing:
            # Direct insert — outgoing doesn't need LLM classification.
            text = extract_dm_text(msg)
            media_kind, media_name = classify_media(msg)
            media_path = (
                await download_media(client, msg, hr.id)
                if media_kind is not None else None
            )
            try:
                async with session_factory() as session:
                    _, saved = await save_outgoing_message(
                        session,
                        OutgoingMessage(
                            hr_id=hr.id,
                            text=text,
                            tg_message_id=msg.id,
                            sent_at=msg.date,
                            media_kind=media_kind,
                            media_path=media_path,
                            media_name=media_name,
                        ),
                    )
                    await session.commit()
                had_new = had_new or saved
            except Exception:
                logger.exception(
                    "backfill outgoing insert failed",
                    extra={"hr_id": hr.id, "tg_message_id": msg.id},
                )
        else:
            # Incoming routed through the same pipeline as live DMs so
            # classification + vacancy-linking stay consistent. The
            # UNIQUE constraint inside save_incoming_message dedupes.
            try:
                await process_dm(
                    msg, lm_client, lm_chat_model, session_factory,
                    client=client,
                    schedule_classification=schedule_classification,
                )
                had_new = True
                # С debounce-планировщиком статус НЕ меняется
                # синхронно — он флипнется через 60с после burst'а.
                # Тогда же отдельный таск пушит on_vacancies_changed
                # сам. Не дублируем сигнал отсюда — в catch-up
                # после OFF→active это особенно важно: 50 сообщений
                # × 30 HR'ов = 1500 пушей за миллисекунду.
                # Без планировщика (legacy путь) — классификация
                # inline, тогда сигнал нужен.
                if (
                    schedule_classification is None
                    and on_vacancies_changed is not None
                ):
                    try:
                        on_vacancies_changed()
                    except Exception:
                        logger.exception(
                            "backfill: on_vacancies_changed hook failed"
                        )
            except Exception:
                logger.exception(
                    "backfill incoming process failed",
                    extra={"hr_id": hr.id, "tg_message_id": msg.id},
                )
    # Delete reconciliation. Window = ids covered by the fetched
    # history; anything in our DB inside that window not present in
    # the response was deleted while we were offline.
    tombstoned = False
    if messages:
        seen_ids = {m.id for m in messages}
        min_id = min(seen_ids)
        async with session_factory() as session:
            local_rows = list(
                (
                    await session.scalars(
                        select(Message).where(
                            Message.hr_id == hr.id,
                            Message.tg_message_id.is_not(None),
                            Message.tg_message_id >= min_id,
                            Message.is_deleted.is_(False),
                        )
                    )
                ).all()
            )
            now = datetime.now(timezone.utc)
            for row in local_rows:
                if row.tg_message_id in seen_ids:
                    continue
                row.is_deleted = True
                if row.is_incoming and row.read_at is None:
                    row.read_at = now
                tombstoned = True
            if tombstoned:
                await session.commit()
    if (had_new or tombstoned) and on_message_persisted is not None:
        try:
            on_message_persisted(hr.id)
        except Exception:
            logger.exception("on_message_persisted hook failed")


async def catch_up_missed_dms(
    client,
    lm_client,
    lm_chat_model,
    session_factory,
    backfill_limit: int,
    *,
    on_message_persisted=None,
    on_vacancies_changed=None,
    schedule_classification=None,
) -> None:
    """Pull recent DM history per known HR, both directions.

    Outgoing messages cover the case where the user typed from their phone
    or another TG client while the bot was off — without this we'd only
    see what we sent from our own app + what HRs sent us, missing half the
    conversation. Повторы отсеивает `save_outgoing_message`: уже лежащая
    строка возвращается с признаком «записали не мы», и догон её не
    считает новой.

    Also reconciles deletes that happened while the bot was offline:
    Telegram doesn't replay ``DeletedMessagesHandler`` updates after a
    reconnect, so any local row whose ``tg_message_id`` falls inside the
    fetched window but is missing from Telegram's response is flipped to
    ``is_deleted=True`` here.
    """
    async with session_factory() as session:
        chats = await list_hrs_for_backfill(session)
    logger.info(
        "DM catch-up: %d HR(s), batch=%d delay=%ss",
        len(chats), _DM_CATCHUP_BATCH_SIZE, _DM_CATCHUP_BATCH_DELAY_SEC,
    )
    # Батчим, чтобы 300-500 HR'ов не превращались в 300-500 последовательных
    # RPC'ов с заметной wall-time'ой. ``asyncio.gather`` внутри батча —
    # параллельно; пауза между батчами даёт TG-rate-limit'у выдохнуть.
    for batch_start in range(0, len(chats), _DM_CATCHUP_BATCH_SIZE):
        batch = chats[batch_start:batch_start + _DM_CATCHUP_BATCH_SIZE]
        results = await asyncio.gather(
            *[
                backfill_hr_dm_history(
                    client, hr, lm_client, lm_chat_model, session_factory,
                    backfill_limit=backfill_limit,
                    on_message_persisted=on_message_persisted,
                    on_vacancies_changed=on_vacancies_changed,
                    schedule_classification=schedule_classification,
                )
                for hr, _last_seen in batch
            ],
            return_exceptions=True,
        )
        for (hr, _), result in zip(batch, results):
            if isinstance(result, Exception):
                logger.exception(
                    "catch_up failed for hr %d", hr.id,
                    exc_info=result,
                )
        if batch_start + _DM_CATCHUP_BATCH_SIZE < len(chats):
            await asyncio.sleep(_DM_CATCHUP_BATCH_DELAY_SEC)


def spawn_hr_backfill(pipeline, hr) -> None:
    """Per-HR DM backfill kicked when a freshly-created HR is wired up
    from a parsed vacancy. Runs as a background task so the parse loop
    doesn't block on Telegram history fetch + media downloads. Pushes
    ``on_new_message`` per HR once the rows land — open chat in UI
    fills in without restart.

    Wajne: вызывать ПОСЛЕ ``try_auto_send`` для свежесозданного HR'а,
    иначе backfill может догнать через ``get_chat_history`` cover-
    letter сообщение раньше, чем ``Bot.send`` закоммитит свою row,
    и вставит её без ``vacancy_id`` (UNIQUE на (hr_id, tg_message_id,
    is_incoming) потом отстрелит Bot.send'овский insert).
    """
    async def _run() -> None:
        try:
            await backfill_hr_dm_history(
                pipeline._client, hr, pipeline._lm_client, pipeline._lm_chat_model,
                pipeline._session_factory,
                backfill_limit=pipeline._rs.dm_backfill_limit,
                on_message_persisted=pipeline.on_new_message,
                on_vacancies_changed=pipeline.on_vacancies_changed,
                schedule_classification=pipeline.schedule_dm_classification,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "spawn_hr_backfill failed for hr %d",
                hr.id, extra={"hr_id": hr.id},
            )
    task = asyncio.create_task(_run())
    pipeline._backfill_tasks.add(task)
    task.add_done_callback(pipeline._backfill_tasks.discard)
