"""Работа агента у бота: обход агрегаторов, вход на сайт, ручной отклик через место прогона и удаление источника."""

import logging
from collections.abc import Awaitable, Callable
from datetime import date
from typing import Literal

from adapters.browser import BrowserHost, find_browser, remove_profile
from backend.agent.availability import current_refusal
from backend.agent.jobs import LoginJob, Source
from backend.agent.kit import AgentKit, SessionPlan
from backend.agent.prompts.frame import system_prompt
from backend.agent.prompts.login import LOGIN_PROMPT, login_task
from backend.agent.sessions import HumanTimeout, LimitExhausted, live_session, run_guarded
from backend.agent.tools_browser import browser_tools
from backend.agent.tools_common import common_tools
from backend.bot import slot
from backend.domain.apply_order import Way
from backend.flows.aggregator_apply import ApplyOrder, apply_phase, apply_vacancy
from backend.flows.aggregator_round import RoundState, seek_source
from backend.models import Aggregator, BotMode, Vacancy
from backend.notify import fire
from backend.repository import aggregators as repo
from backend.telegram_time import utc_now

logger = logging.getLogger(__name__)

AgentOutcome = Literal[slot.CycleOutcome, "missing", "locked", "human_timeout", "limit"]
"""Чем кончилось действие агента: исходы места прогона и свои."""

HUMAN_TIMEOUT_NOTE = "Капча не пройдена — обход снят."
LIMIT_NOTE = "Исчерпан лимит подписки Claude Code — обход снят."
_LOGIN_WAIT_SEC = 3600


def aggregators_available(bot) -> str | None:
    """Почему агент сейчас не может работать; пусто — может."""
    return current_refusal(bot.rs.chat)


def human_done(bot) -> None:
    """«Готово» из окна. Событие asyncio трогается только на цикле бота."""
    slot.on_runner_loop(bot, bot.human_gate.resolve)


async def agent_work(bot, work: Callable[[AgentKit], Awaitable[str]]) -> str:
    """Общая обёртка работы агента: чистая пауза на человека в начале,
    отпущенный ждущий вызов и закрытый браузер в конце, чем бы ни кончилось."""
    kit = _kit(bot)
    kit.gate.reset()
    try:
        return await work(kit)
    except HumanTimeout:
        fire(bot.on_round_note, "on_round_note", HUMAN_TIMEOUT_NOTE)
        return "human_timeout"
    except LimitExhausted:
        fire(bot.on_round_note, "on_round_note", LIMIT_NOTE)
        return "limit"
    finally:
        kit.gate.abort()
        await kit.browser.close()


async def launch_round(bot) -> None:
    """Пустить обход отдельной задачей, если агент может работать и источники есть."""
    if aggregators_available(bot) is not None:
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
    if aggregators_available(bot) is not None:
        return "locked"

    async def work(kit: AgentKit) -> str:
        await _one_source(bot, kit, await _new_round(bot), Source.of(row))
        return "ok"

    return await _in_slot(bot, work, f"aggregator {aggregator_id}")


async def login_aggregator(bot, aggregator_id: int) -> AgentOutcome:
    """Вход: видимый браузер на главной, человек входит и закрывает окно, агент проверяет вход."""
    row = await _row(bot, aggregator_id)
    if row is None or row.host is None:
        return "missing"
    if aggregators_available(bot) is not None:
        return "locked"

    async def work(kit: AgentKit) -> str:
        await kit.browser.open_profile(row.id)
        await kit.browser.show()
        await (await kit.browser.page()).goto(f"https://{row.host}/")
        if not await kit.browser.wait_closed(_LOGIN_WAIT_SEC):
            raise HumanTimeout
        job = LoginJob(Source.of(row))
        plan = SessionPlan(system_prompt(LOGIN_PROMPT), login_task(row.host),
                           [*common_tools(kit, job), *browser_tools(kit, None)], web_search=False)
        if (await run_guarded(kit, plan)).limit_exhausted:
            raise LimitExhausted
        return "ok"

    return await _in_slot(bot, work, f"aggregator login {aggregator_id}")


async def apply_via_agent(bot, vacancy_id: int, way: Way) -> AgentOutcome | Literal["off"]:
    """Ручной отклик выбранным способом: Applied и из Not Fit, Scam, Ghosting.
    Выключенный автоотклик ему не помеха, режим Off — помеха."""
    if await bot.current_mode() is BotMode.OFF:
        return "off"
    async with bot.session_factory() as session:
        if await session.get(Vacancy, vacancy_id) is None:
            return "missing"
    if aggregators_available(bot) is not None:
        return "locked"

    async def work(kit: AgentKit) -> str:
        await apply_vacancy(kit, await _new_round(bot), ApplyOrder(vacancy_id, True, way))
        return "ok"

    return await _in_slot(bot, work, f"apply via agent {vacancy_id}")


async def delete_aggregator(bot, aggregator_id: int) -> str:
    """Удалить агрегатор и его профиль браузера; пока место прогона занято — отказ."""
    if bot.current_poll_task is not None:
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
    """Поиск на источнике, затем отклики по найденному — если автоотклик включён и режим не Off."""
    found = await seek_source(kit, round_, source)
    if found and bot.rs.auto_apply and await bot.current_mode() is not BotMode.OFF:
        await apply_phase(kit, round_, found)


async def _new_round(bot) -> RoundState:
    async with bot.session_factory() as session:
        web = next((a.id for a in await repo.list_aggregators(session) if a.host is None), 0)
    return RoundState(utc_now(), set(), web)


async def _row(bot, aggregator_id: int) -> Aggregator | None:
    async with bot.session_factory() as session:
        return await session.get(Aggregator, aggregator_id)


async def _in_slot(bot, work: Callable[[AgentKit], Awaitable[str]], label: str) -> AgentOutcome:
    outcome, result = await slot.run_in_slot(bot, lambda: agent_work(bot, work), label)
    return result if outcome == "ok" else outcome
