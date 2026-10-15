"""Обход источника-агрегатора: поиск, разбор найденного и передача отобранного."""

import asyncio
import logging
from datetime import datetime

from backend.agent.jobs import Finished, SeekJob, Source
from adapters.claude_code_agent import AgentEnd
from backend.agent.kit import AgentKit, SessionPlan
from backend.agent.prompts.frame import system_prompt
from backend.agent.prompts.seeker import (
    SEEKER_PROMPT, WEB_SEEKER_PROMPT, SeekBounds, seeker_task, web_seeker_task,
)
from backend.agent.sessions import end_reason, run_guarded
from backend.agent.stops import RUN_STOPPERS, LimitExhausted
from backend.agent.tools_browser import browser_tools
from backend.agent.tools_common import common_tools
from backend.agent.tools_seeker import seeker_tools
from backend.flows.handover import hand_over
from backend.flows.parse_queue import ParseQueue
from backend.repository.aggregators import barred_hosts, list_aggregators, mark_run
from backend.repository.profile_languages import read_search_languages
from backend.telegram_time import utc_now

logger = logging.getLogger(__name__)


async def seek_source(kit: AgentKit, source: Source) -> None:
    """Обход одного источника: искатель и конвейер рядом, отобранное — откликателю
    пулом после поиска.

    При сбое источника заведённое до сбоя доразбирается и тоже передаётся:
    вакансия уже в базе, а к оставшимся в New обход не возвращается. Браузер
    поиска закрывается до передачи: отклик открывает тот же профиль, а двух
    окон на один профиль Chromium не откроет.
    """
    job = SeekJob(source, kit.pipeline.rs.aggregator_backfill_limit)
    queue = ParseQueue(kit.pipeline)
    started = utc_now()
    kit.pipeline.emit_progress("aggregator", source.sweep, 0, job.limit)
    try:
        end = await _search(kit, job, queue)
        await queue.drain()
    except (*RUN_STOPPERS, asyncio.CancelledError):
        await queue.stop()
        raise
    except Exception:
        logger.exception("обход источника %s: сбой", source.name)
        await queue.drain()
        await _hand_over(kit, queue)
        return
    if end.limit_exhausted:
        raise LimitExhausted
    await _settle(kit, job, end, started)
    await _hand_over(kit, queue)


async def _hand_over(kit: AgentKit, queue: ParseQueue) -> None:
    await kit.browser.close()
    await hand_over(kit.pipeline, queue.judged)


async def _search(kit: AgentKit, job: SeekJob, queue: ParseQueue) -> AgentEnd:
    """Слепки конвейера освежаются до поиска: обход идёт без приёма каналов,
    который их освежает, и без этого балл был бы нулевым, а чёрный список молчал."""
    await kit.browser.open_profile(job.source.id)
    await kit.browser.clear_cache()
    await kit.pipeline.reload_resources()
    return await run_guarded(kit, await _seek_plan(kit, job, queue))


async def _seek_plan(kit: AgentKit, job: SeekJob, queue: ParseQueue) -> SessionPlan:
    source = job.source
    tools = [*common_tools(kit, job), *seeker_tools(kit, job, queue), *browser_tools(kit, None, None)]
    bounds = SeekBounds(source.last_run_at, job.limit, kit.today, await kit.read(read_search_languages))
    if source.host is not None:
        task = seeker_task(source.host, bounds)
        return SessionPlan(system_prompt(SEEKER_PROMPT, tools), task, tools, web_search=False)
    async with kit.pipeline.session_factory() as session:
        hosts = [a.host for a in await list_aggregators(session) if a.host]
        barred = sorted(await barred_hosts(session))
    task = web_seeker_task(hosts, barred, bounds)
    return SessionPlan(system_prompt(WEB_SEEKER_PROMPT, tools), task, tools, web_search=True)


async def _settle(kit: AgentKit, job: SeekJob, end: AgentEnd, started: datetime) -> None:
    """`last_run_at` двигается только по `finish(done)` и только если модель эмбеддингов отвечала."""
    if isinstance(job.outcome, Finished) and job.outcome.result == "done" and not job.refused:
        await kit.written(lambda session: mark_run(session, job.source.id, started))
        return
    logger.warning("обход источника %s: сбой — %s", job.source.name, end_reason(job, end))
