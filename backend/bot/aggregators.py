"""Работа агента у бота: обход агрегаторов, вход на сайт, ручной отклик через место прогона и удаление источника."""

import logging
from collections.abc import Awaitable, Callable
from datetime import date
from typing import Literal

from adapters.browser import BrowserHost, find_browser, remove_profile
from backend.agent.availability import current_refusal
from backend.agent.jobs import Source
from backend.agent.kit import AgentKit
from backend.agent.sessions import HumanTimeout, LimitExhausted, live_session
from backend.bot import slot
from backend.domain.apply_order import Way
from backend.flows.aggregator_apply import ApplyOrder, apply_phase, apply_vacancy
from backend.flows.aggregator_login import log_in
from backend.flows.aggregator_round import RoundState, seek_source
from backend.models import Aggregator, Vacancy
from backend.notify import fire
from backend.repository import aggregators as repo

logger = logging.getLogger(__name__)

AgentOutcome = Literal[
    slot.CycleOutcome, "missing", "locked", "blacklisted", "human_timeout", "limit",
    "closed", "exhausted", "not_logged_in", "login_timeout",
]
"""Чем кончилось действие агента: исходы места прогона и свои — у источника
(в отсеве), у отклика (вакансия закрыта, способы кончились) и у входа (не
вошёл, окно не закрыто)."""

HUMAN_TIMEOUT_NOTE = "Капча не пройдена — обход снят."
LIMIT_NOTE = "Исчерпан лимит подписки Claude Code — обход снят."


def aggregators_available(bot) -> str | None:
    """Почему агент сейчас не может работать; пусто — может."""
    return current_refusal(bot.rs.chat)


def human_done(bot) -> None:
    """«Готово» из окна. Событие asyncio трогается только на цикле бота."""
    slot.on_runner_loop(bot, bot.human_gate.resolve)


def reveal_browser(bot) -> None:
    """Нажатие на плашку ожидания: вывести браузер вперёд. Задача заводится на цикле бота."""
    slot.on_runner_loop(bot, bot.human_gate.reveal)


async def agent_work(bot, work: Callable[[AgentKit], Awaitable[str]]) -> str:
    """Общая обёртка работы агента: чистая пауза на человека в начале,
    отпущенный ждущий вызов и закрытый браузер в конце, чем бы ни кончилось."""
    kit = _kit(bot)
    kit.gate.reset()
    try:
        return await work(kit)
    except HumanTimeout:
        logger.warning(HUMAN_TIMEOUT_NOTE)
        fire(bot.on_round_note, "on_round_note", HUMAN_TIMEOUT_NOTE)
        return "human_timeout"
    except LimitExhausted:
        logger.warning(LIMIT_NOTE)
        fire(bot.on_round_note, "on_round_note", LIMIT_NOTE)
        return "limit"
    finally:
        kit.gate.abort()
        await kit.browser.close()


async def launch_round(bot) -> None:
    """Пустить обход отдельной задачей, если агент может работать и источники есть.

    Общий выключатель агрегаторов гасит обход целиком, «Поиск по сети» тоже.
    """
    if not bot.rs.aggregators_enabled or aggregators_available(bot) is not None:
        return
    async with bot.session_factory() as session:
        if not await repo.round_sources(session):
            return
    slot.launch_in_slot(bot, lambda: aggregator_round(bot), "aggregator round")


async def aggregator_round(bot) -> None:
    """Обход всех источников; кеш профиля «Поиска по сети» чистится в начале каждого."""

    async def work(kit: AgentKit) -> str:
        async with bot.session_factory() as session:
            sources = [Source.of(row) for row in await repo.round_sources(session)]
        round_ = await _new_round(bot)
        await kit.browser.open_profile(round_.web_search_id)
        await kit.browser.clear_cache()
        for source in sources:
            await _one_source(bot, kit, round_, source)
        return "ok"

    await agent_work(bot, work)


async def run_aggregator_now(bot, aggregator_id: int) -> AgentOutcome:
    """Обход одного источника по кнопке окна."""
    row = await _row(bot, aggregator_id)
    if row is None:
        return "missing"
    if (refusal := await _refused(bot, row)) is not None:
        return refusal

    async def work(kit: AgentKit) -> str:
        await _one_source(bot, kit, await _new_round(bot), Source.of(row))
        return "ok"

    return await _in_slot(bot, work, f"aggregator {aggregator_id}")


async def login_aggregator(bot, aggregator_id: int) -> AgentOutcome:
    """Вход: видимый браузер на главной, человек входит и закрывает окно, агент проверяет вход."""
    row = await _row(bot, aggregator_id)
    if row is None or row.host is None:
        return "missing"
    if (refusal := await _refused(bot, row)) is not None:
        return refusal

    async def work(kit: AgentKit) -> str:
        return await log_in(kit, Source.of(row))

    return await _in_slot(bot, work, f"aggregator login {aggregator_id}")


async def apply_via_agent(bot, vacancy_id: int, way: Way) -> AgentOutcome:
    """Ручной отклик выбранным способом: Applied и из Not Fit, Scam, Ghosting.
    Ни выключенный автоотклик, ни режим ему не помеха: нажал человек."""
    async with bot.session_factory() as session:
        if await session.get(Vacancy, vacancy_id) is None:
            return "missing"
    if aggregators_available(bot) is not None:
        return "locked"

    async def work(kit: AgentKit) -> str:
        outcome = await apply_vacancy(kit, await _new_round(bot), ApplyOrder(vacancy_id, True, way))
        return "ok" if outcome == "applied" else outcome

    return await _in_slot(bot, work, f"apply via agent {vacancy_id}")


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


def _kit(bot) -> AgentKit:
    return AgentKit(
        pipeline=bot.ingestion,
        browser=BrowserHost(find_browser(), bot.rs.show_browser),
        gate=bot.human_gate,
        run_session=live_session(bot.rs.chat.model),
        today=date.today(),
    )


async def _one_source(bot, kit: AgentKit, round_: RoundState, source: Source) -> None:
    """Поиск на источнике, затем отклики по найденному — если автоотклик включён.

    Режим не спрашивается: он решает, запускать ли обход автоматически, а
    запущенный — им или человеком — отрабатывает целиком.
    """
    found = await seek_source(kit, round_, source)
    if found and bot.rs.auto_apply:
        await apply_phase(kit, round_, found)


async def _new_round(bot) -> RoundState:
    async with bot.session_factory() as session:
        web = next((a.id for a in await repo.list_aggregators(session) if a.host is None), 0)
    return RoundState(set(), web)


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


async def _in_slot(bot, work: Callable[[AgentKit], Awaitable[str]], label: str) -> AgentOutcome:
    return await slot.answer_in_slot(bot, lambda: agent_work(bot, work), label)
