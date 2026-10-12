"""Каналы по просьбе окна: заведение нового и чтение по требованию."""

import logging

from typing import Literal

from pyrogram.errors import FloodWait, UsernameInvalid, UsernameNotOccupied

from backend.bot import work
from backend.flows import channels as flow_channels
from backend.telegram_lookup import read_channel_metadata
# из репозитория берутся тёзки методов бота — отсюда псевдонимы
from backend.repository.channels import (
    create_channel,
    find_channel_by_username,
)

logger = logging.getLogger(__name__)

ChannelPollOutcome = Literal[work.WorkOutcome, flow_channels.PollOutcome]
"""Чем кончился прогон одного канала, как это видит окно.

Складывается, а не выписывается: исходы места прогона и исходы самого обхода
объявлены каждый у себя, и переписанные здесь значения разошлись бы с ними.
"""

ChannelAddOutcome = Literal["created", "exists", "invalid", "error"]
"""Чем кончилось заведение канала."""


async def poll_channel_now(bot, channel_id: int) -> ChannelPollOutcome:
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
    """
    return await work.in_slot(
        bot,
        lambda _kit: bot.ingestion.poll_one_channel(channel_id),
        f"manual poll for channel {channel_id}",
    )


async def _ask_telegram_about(bot, username: str):
    """Канал по имени и чем кончился вопрос; исход непустой — дальше не идём.

    Спрашивается один `get_chat`, и он же и есть проверка существования.
    «Не знает такого имени» и «спросить не вышло» разведены нарочно, а чем
    эта разница оборачивается для человека — сказано у зовущего.
    """
    try:
        chat = await bot.client.get_chat(username)
    except (UsernameNotOccupied, UsernameInvalid):
        logger.info("add_channel: Telegram не знает канала @%s", username)
        return None, "invalid"
    except FloodWait as e:
        # Словом, а не трассировкой: это не поломка, а просьба подождать —
        # так же, как у поиска собеседника (`telegram_lookup._quietly`).
        # Срок Telegram называет не всегда, поэтому он идёт строкой.
        logger.warning(
            "add_channel: FloodWait %s на @%s", getattr(e, "value", "?"), username
        )
        return None, "error"
    except Exception:
        logger.exception("add_channel: get_chat(%s) failed", username)
        return None, "error"
    return chat, None


async def add_channel(
    bot, username: str
) -> tuple[int | None, ChannelAddOutcome]:
    """Спросить Telegram об имени и завести канал; номер строки и исход.

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

    chat, refused = await _ask_telegram_about(bot, username)
    if refused is not None:
        return None, refused

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
