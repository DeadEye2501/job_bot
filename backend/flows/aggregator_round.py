"""Обход источника-агрегатора: поиск, где каждая находка проходит весь цикл до отклика."""

import logging
from datetime import datetime

from backend.agent.jobs import Finished, SeekJob, Source
from adapters.claude_code_agent import AgentEnd
from backend.agent.kit import AgentKit, SessionPlan
from backend.agent.prompts.frame import system_prompt
from backend.agent.prompts.seeker import (
    SEEKER_PROMPT, WEB_SEEKER_PROMPT, SeekBounds, seeker_task, web_seeker_task,
)
from backend.agent.sessions import end_reason
from backend.agent.stops import RUN_STOPPERS
from backend.domain.telegram_identity import TELEGRAM_HOSTS
from backend.flows.seeker_run import run_seeker_on
from backend.repository.aggregators import barred_hosts, list_aggregators, mark_run
from backend.repository.profile_languages import read_search_languages
from backend.telegram_time import utc_now

logger = logging.getLogger(__name__)


async def seek_source(kit: AgentKit, source: Source) -> None:
    """Обход одного источника: искатель передаёт находку и ждёт, пока по ней
    пройдёт весь цикл (`tools_seeker`), потом ищет дальше.

    Сбой источника кончает его обход: найденное до сбоя свой цикл уже прошло,
    а недоразобранное после беды доберёт подбор недоразобранного.
    """
    job = SeekJob(source, kit.pipeline.rs.aggregator_backfill_limit)
    started = utc_now()
    kit.pipeline.emit_progress("aggregator", source.sweep, 0, job.limit)
    try:
        end = await _search(kit, job)
    except RUN_STOPPERS:
        raise
    except Exception:
        logger.exception("обход источника %s: сбой", source.name)
        return
    await _settle(kit, job, end, started)


async def _search(kit: AgentKit, job: SeekJob) -> AgentEnd:
    return await run_seeker_on(kit, job, lambda tools: _seek_plan(kit, job, tools))


async def _seek_plan(kit: AgentKit, job: SeekJob, tools: list) -> SessionPlan:
    source = job.source
    bounds = SeekBounds(source.last_run_at, job.limit, kit.today, await kit.read(read_search_languages))
    if source.host is not None:
        task = seeker_task(source.host, bounds)
        return SessionPlan(system_prompt(SEEKER_PROMPT, tools), task, tools, web_search=False)
    async with kit.pipeline.session_factory() as session:
        hosts = [a.host for a in await list_aggregators(session) if a.host] + sorted(TELEGRAM_HOSTS)
        barred = sorted(await barred_hosts(session))
    task = web_seeker_task(hosts, barred, bounds)
    return SessionPlan(system_prompt(WEB_SEEKER_PROMPT, tools), task, tools, web_search=True)


async def _settle(kit: AgentKit, job: SeekJob, end: AgentEnd, started: datetime) -> None:
    """`last_run_at` двигается только по `finish(done)` и только если модель эмбеддингов отвечала."""
    if isinstance(job.outcome, Finished) and job.outcome.result == "done" and not job.refused:
        await kit.written(lambda session: mark_run(session, job.source.id, started))
        return
    logger.warning("обход источника %s: сбой — %s", job.source.name, end_reason(job, end))
