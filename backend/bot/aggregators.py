"""Работа агента у бота с источниками: обход агрегаторов, вход на сайт и удаление источника."""

import logging
from typing import Literal

from adapters.browser import remove_profile
from backend.agent.availability import current_refusal
from backend.agent.jobs import Source
from backend.agent.kit import AgentKit
from backend.bot import slot, work
from backend.flows.aggregator_login import log_in
from backend.flows.aggregator_round import seek_source
from backend.models import Aggregator
from backend.repository import aggregators as repo

logger = logging.getLogger(__name__)

AgentOutcome = Literal[
    work.WorkOutcome, "missing", "locked", "blacklisted",
    "not_logged_in", "login_timeout",
]
"""Чем кончилось действие агента: исходы места прогона и свои — у источника
(в отсеве) и у входа (не вошёл, окно не закрыто)."""


def aggregators_available(bot) -> str | None:
    """Почему агент сейчас не может работать; пусто — может."""
    return current_refusal(bot.rs.chat)


def human_done(bot) -> None:
    """«Готово» из окна. Событие asyncio трогается только на цикле бота."""
    slot.on_runner_loop(bot, bot.human_gate.resolve)


def reveal_browser(bot) -> None:
    """Нажатие на плашку ожидания: вывести браузер вперёд. Задача заводится на цикле бота."""
    slot.on_runner_loop(bot, bot.human_gate.reveal)


async def seek_all(bot, kit: AgentKit) -> None:
    """Обход всех источников внутри оборота; кеш профиля «Поиска по сети» чистится в начале.

    Общий выключатель агрегаторов гасит обход целиком, «Поиск по сети» тоже;
    не готов агент или источников нет — обхода нет.
    """
    if not bot.rs.aggregators_enabled or aggregators_available(bot) is not None:
        return
    async with bot.session_factory() as session:
        sources = [Source.of(row) for row in await repo.round_sources(session)]
        web_search = await repo.web_search_id(session)
    if not sources:
        return
    await kit.browser.open_profile(web_search)
    await kit.browser.clear_cache()
    for source in sources:
        await seek_source(kit, source)


async def run_aggregator_now(bot, aggregator_id: int) -> AgentOutcome:
    """Обход одного источника по кнопке окна."""
    row = await _row(bot, aggregator_id)
    if row is None:
        return "missing"
    if (refusal := await _refused(bot, row)) is not None:
        return refusal

    async def one_source(kit: AgentKit) -> str:
        await seek_source(kit, Source.of(row))
        return "ok"

    return await work.in_slot(bot, one_source, f"aggregator {aggregator_id}")


async def login_aggregator(bot, aggregator_id: int) -> AgentOutcome:
    """Вход: видимый браузер на главной, человек входит и закрывает окно, агент проверяет вход."""
    row = await _row(bot, aggregator_id)
    if row is None or row.host is None:
        return "missing"
    if (refusal := await _refused(bot, row)) is not None:
        return refusal

    async def login(kit: AgentKit) -> str:
        return await log_in(kit, Source.of(row))

    return await work.in_slot(bot, login, f"aggregator login {aggregator_id}")


async def delete_aggregator(bot, aggregator_id: int) -> str:
    """Удалить агрегатор и его профиль браузера; пока место прогона занято — отказ."""
    if slot.slot_taken(bot):
        return "busy"
    async with bot.session_factory() as session:
        async with session.begin():
            outcome = await repo.delete_aggregator(session, aggregator_id)
    if outcome == "ok":
        remove_profile(aggregator_id)
    return outcome


async def _row(bot, aggregator_id: int) -> Aggregator | None:
    async with bot.session_factory() as session:
        return await session.get(Aggregator, aggregator_id)


async def _refused(bot, row: Aggregator) -> AgentOutcome | None:
    """Чем отказать в ручной работе с сайтом; пусто — можно.

    Сайт в отсеве руками не обходят и на него не входят — отметку снимают;
    отсев старше запора агента: запор погаснет сам, а отметка — нет.
    """
    async with bot.session_factory() as session:
        if await repo.aggregator_blacklist_value(session, row) is not None:
            return "blacklisted"
    return "locked" if aggregators_available(bot) is not None else None
