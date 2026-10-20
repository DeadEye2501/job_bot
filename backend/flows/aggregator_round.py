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
from backend.agent.sessions import end_reason, run_seeker, seeker_plan
from backend.agent.stops import RUN_STOPPERS
from backend.agent.tools_browser import browser_tools
from backend.agent.tools_common import common_tools
from backend.agent.tools_seeker import seeker_tools
from backend.domain.telegram_identity import TELEGRAM_HOSTS
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


async def open_clean_profile(kit: AgentKit, source_id: int) -> None:
    """Профиль источника с чистым кешем: выдача приходит свежей, а не из
    прошлого обхода."""
    await kit.browser.open_profile(source_id)
    await kit.browser.clear_cache()


async def _search(kit: AgentKit, job: SeekJob) -> AgentEnd:
    """Слепки конвейера освежаются до поиска: обход идёт без приёма каналов,
    который их освежает, и без этого балл был бы нулевым, а чёрный список молчал."""
    await open_clean_profile(kit, job.source.id)
    await kit.pipeline.reload_resources()
    return await run_seeker(kit, job, await _seek_plan(kit, job))


async def _seek_plan(kit: AgentKit, job: SeekJob) -> SessionPlan:
    source = job.source
    tools = [*common_tools(kit, job), *seeker_tools(kit, job), *browser_tools(kit, None, None)]
    bounds = SeekBounds(source.last_run_at, job.limit, kit.today, await kit.read(read_search_languages))
    if source.host is not None:
        task = seeker_task(source.host, bounds)
        return seeker_plan(kit, job, SessionPlan(system_prompt(SEEKER_PROMPT, tools), task, tools, web_search=False))
    async with kit.pipeline.session_factory() as session:
        hosts = [a.host for a in await list_aggregators(session) if a.host] + sorted(TELEGRAM_HOSTS)
        barred = sorted(await barred_hosts(session))
    task = web_seeker_task(hosts, barred, bounds)
    return seeker_plan(kit, job, SessionPlan(system_prompt(WEB_SEEKER_PROMPT, tools), task, tools, web_search=True))


async def _settle(kit: AgentKit, job: SeekJob, end: AgentEnd, started: datetime) -> None:
    """`last_run_at` двигается только по `finish(done)` и только если модель эмбеддингов отвечала."""
    if isinstance(job.outcome, Finished) and job.outcome.result == "done" and not job.refused:
        await kit.written(lambda session: mark_run(session, job.source.id, started))
        return
    logger.warning("обход источника %s: сбой — %s", job.source.name, end_reason(job, end))
