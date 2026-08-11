"""Обход телеграм-каналов за свежими постами."""

import logging

from sqlalchemy import select

from backend.helpers import fetch_telegram_avatar
from backend.models import TelegramChannel

from backend.flows import ingest
from backend.notify import fire

logger = logging.getLogger(__name__)


async def poll_active_channels(pipeline) -> None:
    await pipeline._reload_resources()
    # Берём ВСЕ каналы с @username (не только active=true): metadata-
    # sweep должен подтягивать title и аватарки и для выключенных
    # каналов тоже — они всё равно показываются в UI и пользователь
    # ожидает свежие данные. Активность гейтит только обработку
    # сообщений ниже.
    async with pipeline._session_factory() as session:
        channels = (
            await session.scalars(
                select(TelegramChannel).where(
                    TelegramChannel.username.is_not(None)
                )
            )
        ).all()
    all_named = list(channels)

    # Быстрый sweep метаданных по всему списку до тяжёлой обработки
    # сообщений: один `get_chat` на канал, плюс backfill аватара через
    # `download_media`, всё пишется одной транзакцией. UI получает
    # свежие названия и аватары за десятки секунд, а не за десятки
    # минут (по ~5 мин на канал на парсинг сообщений).
    await refresh_channel_metadata(pipeline, all_named)

    active_named = [c for c in all_named if c.is_active]
    total = len(active_named)
    logger.info(
        "Poll cycle start: %d named channels (%d active)",
        len(all_named),
        total,
    )
    for idx, ch in enumerate(active_named):
        pipeline._emit_progress("channel", f"@{ch.username}", idx, total)
        try:
            await poll_channel(pipeline, 
                ch.id, ch.username, ch.last_processed_msg_id
            )
        except Exception:
            logger.exception("[@%s] poll failed", ch.username)
    pipeline._emit_progress("channel", "", total, total)
    # 0/0 on the message track signals the UI to clear that bar between
    # cycles; otherwise it would freeze on the last channel's count.
    pipeline._emit_progress("message", "", 0, 0)
    logger.info("Poll cycle done")


async def poll_one_channel(pipeline, channel_id: int) -> bool:
    """Run metadata refresh + message polling for a single channel.

    UI's «Прогнать сейчас» — taps this without touching the global
    poll loop, so it doesn't have to wait through 17 other channels
    in a 90-min cycle. Returns False if the row is missing/без
    username, либо если сам poll сломался (FloodWait, ChannelPrivate,
    LLM-таймаут) — то же поведение, что у глобального цикла, чтобы
    не давать `_dispatch` ловить и сжирать exception без `action`.
    """
    await pipeline._reload_resources()
    async with pipeline._session_factory() as session:
        ch = await session.get(TelegramChannel, channel_id)
        if ch is None or not ch.username:
            return False
        username = ch.username
        last_id = ch.last_processed_msg_id
    await refresh_channel_metadata_for_ids(pipeline, [channel_id])
    try:
        await poll_channel(pipeline, channel_id, username, last_id)
    except Exception:
        logger.exception("[@%s] manual poll failed", username)
        return False
    return True


async def refresh_channel_metadata_for_ids(pipeline, channel_ids: list[int]) -> None:
    """Public entry point for one-off metadata refresh — например,
    после ручного «Добавить канал» из UI: сразу же тянем title/avatar,
    чтобы пользователь не ждал следующего поллинга.
    Делегирует во внутренний sweep, который и кидает on_channels_changed.
    """
    if not channel_ids:
        return
    logger.debug("refresh metadata for %d channel(s)", len(channel_ids))
    async with pipeline._session_factory() as session:
        rows = (
            await session.scalars(
                select(TelegramChannel).where(TelegramChannel.id.in_(channel_ids))
            )
        ).all()
    await refresh_channel_metadata(pipeline, list(rows))


async def refresh_channel_metadata(pipeline, channels) -> None:
    """Sweep metadata for every active channel before message polling.

    One `get_chat` call per channel (sequential — Pyrogram's session is
    not thread-safe and concurrent calls can trip FloodWait); the same
    response carries both ``title`` and ``photo``. Title is updated on
    every change; avatar is backfill-only (matches the HR policy in
    ``refresh_hr_from_telegram`` — once captured, we don't overwrite). All
    diffs land in a single transaction. Failures are logged and skipped.
    """
    title_updates: dict[int, str] = {}
    avatar_updates: dict[int, bytes] = {}
    for ch in channels:
        try:
            chat = await pipeline._client.get_chat(ch.username)
        except Exception:
            logger.exception("[@%s] get_chat failed", ch.username)
            continue
        if chat is None:
            continue
        new_title = getattr(chat, "title", None)
        if new_title and new_title != ch.title:
            title_updates[ch.id] = new_title
        if ch.avatar is None and getattr(chat, "photo", None) is not None:
            blob = await fetch_telegram_avatar(pipeline._client, chat)
            if blob:
                avatar_updates[ch.id] = blob
    if not title_updates and not avatar_updates:
        return
    touched_ids = set(title_updates) | set(avatar_updates)
    async with pipeline._session_factory() as session:
        for channel_id in touched_ids:
            db_ch = await session.get(TelegramChannel, channel_id)
            if db_ch is None:
                continue
            new_title = title_updates.get(channel_id)
            if new_title is not None and db_ch.title != new_title:
                db_ch.title = new_title
            blob = avatar_updates.get(channel_id)
            if blob is not None and db_ch.avatar is None:
                db_ch.avatar = blob
        await session.commit()
    logger.info(
        "refresh_channel_metadata: %d title(s), %d avatar(s) updated",
        len(title_updates), len(avatar_updates),
    )
    fire(pipeline.on_channels_changed, "on_channels_changed")


async def poll_channel(
    pipeline,
    channel_id: int,
    channel_username: str,
    last_id: int | None,
) -> None:
    new_msgs = []
    async for msg in pipeline._client.get_chat_history(
        channel_username, limit=pipeline._rs.backfill_limit
    ):
        if last_id is not None and msg.id <= last_id:
            break
        new_msgs.append(msg)

    ordered = list(reversed(new_msgs))
    total = len(ordered)
    # Cursor flush'ится батчами вместо коммита на каждое сообщение —
    # backfill_limit=15 × 50 каналов = ~750 fsync'ов на цикл иначе.
    # При crash mid-batch потеряем до BATCH_FLUSH_EVERY-1 уже-обработанных
    # сообщений (они реингестятся, дедуп по embedding'у не пропустит).
    # finally-flush гарантирует, что курсор не отстаёт между poll-циклами.
    BATCH_FLUSH_EVERY = 10
    cursor: int | None = None
    try:
        for i, msg in enumerate(ordered):
            pipeline._emit_progress("message", f"@{channel_username}", i, total)
            try:
                await ingest.ingest_post(pipeline, channel_id, channel_username, msg)
            except Exception:
                # Advance cursor anyway — иначе сломанное сообщение
                # реингестится бесконечно. Дубликаты (если ingest
                # частично прошёл) всё равно срежет дедуп.
                logger.exception(
                    "[@%s] %d ingest failed, advancing cursor",
                    channel_username, msg.id,
                )
            cursor = msg.id
            if (i + 1) % BATCH_FLUSH_EVERY == 0:
                await advance_cursor(pipeline, channel_id, cursor)
        pipeline._emit_progress("message", f"@{channel_username}", total, total)
    finally:
        if cursor is not None:
            await advance_cursor(pipeline, channel_id, cursor)


async def advance_cursor(pipeline, channel_id: int, msg_id: int) -> None:
    async with pipeline._session_factory() as session:
        ch = await session.get(TelegramChannel, channel_id)
        if ch is None:
            return
        ch.last_processed_msg_id = msg_id
        await session.commit()
    logger.debug(
        "advance_cursor: channel=%d -> msg_id=%d", channel_id, msg_id,
    )
