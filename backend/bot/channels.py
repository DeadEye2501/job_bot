"""Правка каналов из окна: заведение, удаление, чтение по требованию."""

import logging

from typing import Literal

from pyrogram.errors import FloodWait, UsernameInvalid, UsernameNotOccupied

from backend.bot import aggregators, slot
from backend.flows import channels as flow_channels
from backend.telegram_lookup import read_channel_metadata
# из репозитория берутся тёзки методов бота — отсюда псевдонимы
from backend.repository.channels import (
    create_channel,
    find_channel_by_username,
)

logger = logging.getLogger(__name__)

ChannelPollOutcome = Literal[slot.CycleOutcome, flow_channels.PollOutcome]
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


async def ingest_round(bot) -> None:
    """Оборот приёма: сперва дочитать отложенное, потом идти за новым.

    Недоразобранная строка ждёт статьи, которой не хватило на приёме, и в
    окне её не видно вовсе — ни в списке, ни в отказах. Подбирай такие только
    при подъёме, и объявление ждало бы до следующего запуска приложения, а
    работает оно сутками.

    Сорвавшийся подбор обход не отменяет: свежие объявления человек ждёт
    больше, чем дочитанные.
    """
    try:
        await bot.ingestion.recover_orphan_vacancies()
    except Exception:
        logger.exception("orphan recovery failed")
    await bot.ingestion.poll_active_channels()


async def force_poll_once(bot) -> slot.CycleOutcome:
    """Кнопка ▶: тот же оборот, что у цикла, — недоразобранное, каналы, затем
    агрегаторы, — но в любом режиме: человек нажал сам и ждёт, что что-то
    произойдёт.

    Выключатели каналов и агрегаторов действуют как в цикле: выключенному
    просто нечего опрашивать. «busy» — место прогона занято; погашенный или
    сорвавшийся опрос каналов обход агрегаторов не пускает.
    """
    outcome, _ = await slot.run_in_slot(bot, lambda: ingest_round(bot), "forced poll cycle")
    if outcome != "ok" or bot.stop_event.is_set():
        return outcome
    await aggregators.launch_round(bot)
    return "ok"
