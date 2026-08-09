"""Правка каналов из окна: заведение, удаление, чтение по требованию."""

import logging
import asyncio

from typing import Literal

from backend.helpers import fetch_telegram_avatar
# из репозитория берутся тёзки методов бота — отсюда псевдонимы
from backend.repository.channels import (
    delete_channel as repo_delete_channel,
    find_channel_by_username,
    reset_channel_cursor as repo_reset_channel_cursor,
)

logger = logging.getLogger(__name__)


async def poll_channel_now(
    bot, channel_id: int
) -> Literal["ok", "busy", "missing", "cancelled", "error"]:
    """UI «Прогнать сейчас» — single-channel manual poll.

    Wraps the same `_current_poll_task` slot + `on_cycle_start/end`
    hooks as the global cycle so the bottom-bar progress indicator,
    stop-button (`cancel_current_poll`), и all other "идёт цикл"
    UI affordances работают одинаково для ручного single-channel
    прогона.

    Returns a status string so the bridge can give a tailored toast
    for each outcome instead of one generic «не найден» error:
    - "ok": cycle ran end-to-end.
    - "busy": another cycle was already in flight (skip).
    - "missing": channel row не существует / без @username.
    - "cancelled": user clicked stop mid-poll.
    - "error": unexpected exception inside `poll_one_channel`.
    """
    if bot._current_poll_task is not None:
        logger.info(
            "poll_channel_now: another cycle is running, skipping (channel_id=%d)",
            channel_id,
        )
        return "busy"
    if bot.on_cycle_start is not None:
        try: bot.on_cycle_start()
        except Exception: logger.exception("on_cycle_start hook failed")
    status: Literal["ok", "missing", "cancelled", "error"] = "ok"
    try:
        bot._current_poll_task = asyncio.create_task(
            bot._ingestion.poll_one_channel(channel_id)
        )
        try:
            ok = await bot._current_poll_task
            if not ok:
                status = "missing"
        except asyncio.CancelledError:
            logger.info(
                "manual poll for channel %d cancelled by user", channel_id
            )
            status = "cancelled"
    except Exception:
        logger.exception("manual single-channel poll failed (channel_id=%d)", channel_id)
        status = "error"
    finally:
        bot._current_poll_task = None
        if bot.on_cycle_end is not None:
            try: bot.on_cycle_end()
            except Exception: logger.exception("on_cycle_end hook failed")
    return status


async def reset_channel_cursor(bot, channel_id: int) -> bool:
    """UI «Сбросить курсор» — clears last_processed_msg_id."""
    async with bot._session_factory() as session:
        async with session.begin():
            return await repo_reset_channel_cursor(session, channel_id)


async def delete_channel(bot, channel_id: int) -> int | None:
    """UI «Удалить канал» — severs vacancy FKs and deletes the row.
    Returns count of detached vacancies, or None if channel missing.
    """
    async with bot._session_factory() as session:
        async with session.begin():
            return await repo_delete_channel(session, channel_id)


async def add_channel(
    bot, username: str
) -> tuple[int | None, Literal["created", "exists", "invalid"]]:
    """Validate against Telegram and insert a TelegramChannel.

    Returns a status tuple:
    - ``(id, "exists")`` — row уже была; UI выбирает её и тостит «уже добавлен».
    - ``(id, "created")`` — новая строка с подгруженными title/avatar.
    - ``(None, "invalid")`` — Telegram не знает такой канал; ничего
      не пишем в БД, чтобы пользователь не накапливал зомби-ряды без
      title/avatar после опечаток.

    Метаданные тянем ДО инсёрта одним `get_chat`-вызовом — он же
    выступает валидатором существования.
    """
    async with bot._session_factory() as session:
        existing = await find_channel_by_username(session, username)
        if existing is not None:
            return existing.id, "exists"

    try:
        chat = await bot._client.get_chat(username)
    except Exception as e:
        logger.warning(
            "add_channel: get_chat(%s) failed: %s: %s",
            username, type(e).__name__, e,
        )
        return None, "invalid"
    if chat is None:
        return None, "invalid"

    title = getattr(chat, "title", None)
    avatar = (
        await fetch_telegram_avatar(bot._client, chat)
        if getattr(chat, "photo", None) is not None
        else None
    )

    async with bot._session_factory() as session:
        async with session.begin():
            # Race-guard: ещё одна вкладка/процесс могла успеть вставить
            # за время `get_chat` — повторно проверяем дубль.
            existing = await find_channel_by_username(session, username)
            if existing is not None:
                return existing.id, "exists"
            from backend.models import TelegramChannel
            ch = TelegramChannel(
                username=username.lower(),
                title=title,
                is_active=True,
                avatar=avatar,
            )
            session.add(ch)
            await session.flush()
            channel_id = ch.id
    return channel_id, "created"


def cancel_current_poll(bot) -> None:
    """Cancel an in-flight poll cycle without stopping the whole bot.

    Thread-safe: см. ``kick``. Task.cancel() из чужого треда мутирует
    внутреннее состояние Task'а и пытается loop.call_soon — обязан
    идти через call_soon_threadsafe.
    """
    task = bot._current_poll_task
    if task is None or task.done():
        return
    logger.info("Cancel current poll requested")
    loop = bot._loop
    if loop is not None and not loop.is_closed():
        loop.call_soon_threadsafe(task.cancel)
    else:
        task.cancel()


async def force_poll_once(bot) -> Literal["ok", "busy", "cancelled", "error"]:
    """Manual one-shot poll, fired regardless of bot_state.mode. Used by
    the refresh button so the user always sees something happen.

    Returns "busy" if another cycle is already running (UI's stop button
    takes precedence) — two concurrent cycles would race on the embedding
    cache and the channel cursor. UI surfaces "busy" as a toast.
    """
    if bot._current_poll_task is not None:
        logger.info("force_poll_once: another cycle is already running, skipping")
        return "busy"
    if bot.on_cycle_start is not None:
        try: bot.on_cycle_start()
        except Exception: logger.exception("on_cycle_start hook failed")
    status: Literal["ok", "cancelled", "error"] = "ok"
    try:
        bot._current_poll_task = asyncio.create_task(
            bot._ingestion.poll_active_channels()
        )
        try:
            await bot._current_poll_task
        except asyncio.CancelledError:
            logger.info("forced poll cycle cancelled by user")
            status = "cancelled"
    except Exception:
        logger.exception("forced poll cycle failed")
        status = "error"
    finally:
        bot._current_poll_task = None
        if bot.on_cycle_end is not None:
            try: bot.on_cycle_end()
            except Exception: logger.exception("on_cycle_end hook failed")
    return status
