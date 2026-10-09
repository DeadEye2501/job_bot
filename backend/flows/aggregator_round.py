"""Обход источников-агрегаторов: фаза поиска одного источника."""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime

from backend.agent.jobs import Finished, SeekJob, Source
from adapters.claude_code_agent import AgentEnd
from backend.agent.kit import AgentKit, SessionPlan
from backend.agent.prompts.frame import system_prompt
from backend.agent.prompts.seeker import SEEKER_PROMPT, WEB_SEEKER_PROMPT, seeker_task, web_seeker_task
from backend.agent.sessions import HumanTimeout, LimitExhausted, run_guarded
from backend.agent.tools_browser import browser_tools
from backend.agent.tools_common import common_tools
from backend.agent.tools_seeker import seeker_tools
from backend.flows.parse_queue import ParseQueue
from backend.repository.aggregators import list_aggregators, mark_run
from backend.telegram_time import utc_now

logger = logging.getLogger(__name__)


@dataclass
class RoundState:
    """Один обход: когда начат, какие агрегаторы закрыты до его конца, чей профиль у «Поиска по сети»."""

    started_at: datetime
    closed_aggregators: set[int]
    web_search_id: int


async def seek_source(kit: AgentKit, round_: RoundState, source: Source) -> list[int]:
    """Фаза 1 одного источника: искатель и конвейер рядом. Ответ — заведённое искателем.

    При сбое источника заведённое до сбоя доразбирается и тоже отдаётся:
    вакансия уже в базе, а к оставшимся в New обход не возвращается.
    """
    job = SeekJob(source, kit.pipeline.rs.aggregator_backfill_limit)
    queue = ParseQueue(kit.pipeline)
    started = utc_now()
    kit.pipeline.emit_progress("aggregator", f"{source.name} — найдено", 0, job.limit)
    try:
        end = await _search(kit, job, queue)
        await queue.drain()
    except (HumanTimeout, LimitExhausted, asyncio.CancelledError):
        await queue.stop()
        raise
    except Exception:
        logger.exception("обход источника %s: сбой", source.name)
        await queue.drain()
        return job.found
    if end.limit_exhausted:
        raise LimitExhausted
    await _settle(kit, job, end, started)
    return job.found


async def _search(kit: AgentKit, job: SeekJob, queue: ParseQueue) -> AgentEnd:
    """Слепки конвейера освежаются до поиска: обход идёт без приёма каналов,
    который их освежает, и без этого балл был бы нулевым, а чёрный список молчал."""
    await kit.browser.open_profile(job.source.id)
    await kit.browser.clear_cache()
    await kit.pipeline.reload_resources()
    return await run_guarded(kit, await _seek_plan(kit, job, queue))


async def _seek_plan(kit: AgentKit, job: SeekJob, queue: ParseQueue) -> SessionPlan:
    source = job.source
    tools = [*common_tools(kit, job), *seeker_tools(kit, job, queue), *browser_tools(kit, None)]
    if source.host is not None:
        task = seeker_task(source.host, source.last_run_at, job.limit, kit.today)
        return SessionPlan(system_prompt(SEEKER_PROMPT), task, tools, web_search=False)
    async with kit.pipeline.session_factory() as session:
        hosts = [a.host for a in await list_aggregators(session) if a.host]
    task = web_seeker_task(hosts, source.last_run_at, job.limit, kit.today)
    return SessionPlan(system_prompt(WEB_SEEKER_PROMPT), task, tools, web_search=True)


async def _settle(kit: AgentKit, job: SeekJob, end: AgentEnd, started: datetime) -> None:
    """`last_run_at` двигается только по `finish(done)` и только если модель эмбеддингов отвечала."""
    if isinstance(job.outcome, Finished) and job.outcome.result == "done" and not job.refused:
        async with kit.pipeline.session_factory() as session:
            async with session.begin():
                await mark_run(session, job.source.id, started)
        return
    reason = job.outcome.reason if isinstance(job.outcome, Finished) else end.detail
    logger.warning("обход источника %s: сбой — %s", job.source.name, reason or "без итога")
