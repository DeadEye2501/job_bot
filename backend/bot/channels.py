"""Правка каналов из окна: заведение, удаление, чтение по требованию."""

import logging

from typing import Literal

from backend.bot import slot
from backend.helpers import fetch_telegram_avatar
# из репозитория берутся тёзки методов бота — отсюда псевдонимы
from backend.repository.channels import (
    create_channel,
    delete_channel as repo_delete_channel,
    find_channel_by_username,
    reset_channel_cursor as repo_reset_channel_cursor,
)

logger = logging.getLogger(__name__)


async def poll_channel_now(
    bot, channel_id: int
) -> Literal["ok", "busy", "missing", "cancelled", "error"]:
    """UI «Прогнать сейчас» — single-channel manual poll.

    Идёт в общем месте прогона, как и полный обход: отсюда нижняя полоса
    прогресса, кнопка «остановить» (`cancel_current_poll`) и все прочие
    «идёт цикл» приметы окна работают одинаково для ручного прогона
    одного канала.

    Returns a status string so the bridge can give a tailored toast
    for each outcome instead of one generic «не найден» error:
    - "ok": cycle ran end-to-end.
    - "busy": another cycle was already in flight (skip).
    - "missing": channel row не существует / без @username.
    - "cancelled": user clicked stop mid-poll.
    - "error": unexpected exception inside `poll_one_channel`.
    """
    outcome, ok = await slot.run_in_slot(
        bot,
        lambda: bot._ingestion.poll_one_channel(channel_id),
        f"manual poll for channel {channel_id}",
    )
    if outcome == "ok" and not ok:
        return "missing"
    return outcome


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
            channel_id = await create_channel(session, username, title, avatar)
    return channel_id, "created"


async def force_poll_once(bot) -> Literal["ok", "busy", "cancelled", "error"]:
    """Manual one-shot poll, fired regardless of bot_state.mode. Used by
    the refresh button so the user always sees something happen.

    Отдаёт "busy", если место прогона занято, — окно показывает это
    подсказкой.
    """
    outcome, _ = await slot.run_in_slot(
        bot, lambda: bot._ingestion.poll_active_channels(), "forced poll cycle"
    )
    return outcome
