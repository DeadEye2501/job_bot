"""Правка каналов из окна: заведение, удаление, чтение по требованию."""

import logging

from typing import Literal

from pyrogram.errors import UsernameInvalid, UsernameNotOccupied

from backend.bot import slot
from backend.telegram_lookup import read_channel_metadata
# из репозитория берутся тёзки методов бота — отсюда псевдонимы
from backend.repository.channels import (
    create_channel,
    delete_channel as repo_delete_channel,
    find_channel_by_username,
)

logger = logging.getLogger(__name__)


async def poll_channel_now(
    bot, channel_id: int
) -> Literal["ok", "busy", "missing", "blacklisted", "cancelled", "error"]:
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
    - "blacklisted": канал в чёрном списке — руками его тоже не прогоняют.
    - "cancelled": user clicked stop mid-poll.
    - "error": обход сломался — закрытый канал, просьба подождать, молчание
      модели. Своё слово ему нужно: «не найден» послал бы человека искать
      запись, которая на месте, а причина осталась бы только в журнале.

    Место прогона отвечает о своём — занято, отменено, сорвалось наружу, — а
    об исходе самого обхода говорит он сам, и его ответ сильнее: место видит
    удачей всё, что не бросило исключение.
    """
    outcome, walk = await slot.run_in_slot(
        bot,
        lambda: bot.ingestion.poll_one_channel(channel_id),
        f"manual poll for channel {channel_id}",
    )
    return walk if outcome == "ok" else outcome


async def delete_channel(bot, channel_id: int) -> int | None:
    """UI «Удалить канал» — severs vacancy FKs and deletes the row.
    Returns count of detached vacancies, or None if channel missing.
    """
    async with bot.session_factory() as session:
        async with session.begin():
            return await repo_delete_channel(session, channel_id)


async def add_channel(
    bot, username: str
) -> tuple[int | None, Literal["created", "exists", "invalid", "error"]]:
    """Validate against Telegram and insert a TelegramChannel.

    Returns a status tuple:
    - ``(id, "exists")`` — row уже была; UI выбирает её и тостит «уже добавлен».
    - ``(id, "created")`` — новая строка с подгруженными title/avatar.
    - ``(None, "invalid")`` — Telegram не знает такого имени; ничего
      не пишем в БД, чтобы пользователь не накапливал зомби-ряды без
      title/avatar после опечаток.
    - ``(None, "error")`` — спросить Telegram не вышло вовсе: сеть, запрет
      частоты, закрытый канал. Имя при этом может быть верным, и говорить
      человеку «проверьте имя» здесь нельзя.

    Метаданные тянем ДО инсёрта одним `get_chat`-вызовом — он же
    выступает валидатором существования.
    """
    async with bot.session_factory() as session:
        existing = await find_channel_by_username(session, username)
        if existing is not None:
            return existing.id, "exists"

    try:
        chat = await bot.client.get_chat(username)
    except (UsernameNotOccupied, UsernameInvalid):
        logger.info("add_channel: Telegram не знает канала @%s", username)
        return None, "invalid"
    except Exception:
        logger.exception("add_channel: get_chat(%s) failed", username)
        return None, "error"
    if chat is None:
        return None, "invalid"

    title, avatar = await read_channel_metadata(bot.client, chat)

    async with bot.session_factory() as session:
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
        bot, lambda: bot.ingestion.poll_active_channels(), "forced poll cycle"
    )
    return outcome
