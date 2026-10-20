"""Каналы по просьбе окна: заведение нового и чтение по требованию."""

from typing import Literal

from backend.bot import work
from backend.flows import channels as flow_channels
from backend.telegram_lookup import TelegramTrouble, ask_telegram, read_channel_metadata
# из репозитория берутся тёзки методов бота — отсюда псевдонимы
from backend.repository.channels import (
    create_channel,
    find_channel_by_username,
)

ChannelPollOutcome = Literal[work.WorkOutcome, flow_channels.PollOutcome]
"""Чем кончился прогон одного канала, как это видит окно.

Складывается, а не выписывается: исходы места прогона и исходы самого обхода
объявлены каждый у себя, и переписанные здесь значения разошлись бы с ними.
"""

ChannelAddOutcome = Literal["created", "exists", TelegramTrouble]
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


async def add_channel(
    bot, username: str
) -> tuple[int | None, ChannelAddOutcome]:
    """Спросить Telegram об имени и завести канал; номер строки и исход.

    Returns a status tuple:
    - ``(id, "exists")`` — row уже была; UI выбирает её и тостит «уже добавлен».
    - ``(id, "created")`` — новая строка с подгруженными title/avatar.
    - ``(None, беда)`` — слово беды Telegram (`ask_telegram`); ничего не пишем
      в БД, чтобы пользователь не накапливал зомби-ряды без title/avatar
      после опечаток.

    Метаданные тянем ДО инсёрта одним `get_chat`-вызовом — он же
    выступает валидатором существования.
    """
    async with bot.session_factory() as session:
        existing = await find_channel_by_username(session, username)
        if existing is not None:
            return existing.id, "exists"

    chat, trouble = await ask_telegram(f"add_channel @{username}", lambda: bot.client.get_chat(username))
    if trouble is not None:
        return None, trouble

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
