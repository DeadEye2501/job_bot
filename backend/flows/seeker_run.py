"""Сессия искателя на чистом профиле его источника — одна у обхода агрегатора и
у страницы, принесённой человеком; чистым профиль «Поиска по сети» бот делает
и перед всем оборотом.

Отдельно от обхода (`aggregator_round`): страница человека обходом не
является, а сессию берёт ту же.
"""

from collections.abc import Awaitable, Callable

from adapters.claude_code_agent import AgentEnd
from backend.agent.jobs import SeekJob
from backend.agent.kit import AgentKit, SessionPlan
from backend.agent.sessions import run_seeker
from backend.agent.tools_browser import browser_tools
from backend.agent.tools_common import common_tools
from backend.agent.tools_seeker import seeker_tools


async def open_clean_profile(kit: AgentKit, source_id: int) -> None:
    """Профиль источника с чистым кешем: выдача приходит свежей, а не из
    прошлого обхода."""
    await kit.browser.open_profile(source_id)
    await kit.browser.clear_cache()


async def run_seeker_on(
    kit: AgentKit, job: SeekJob, plan_of: Callable[[list], Awaitable[SessionPlan]]
) -> AgentEnd:
    """Сессия искателя: чистый кеш, свежие слепки, инструменты, сроки искателя.

    `plan_of(tools)` собирает план из инструментов — наставление и задание у
    каждого зовущего своё. Слепки конвейера освежаются до сессии: обход идёт
    без приёма каналов, который их освежает, и без этого балл был бы нулевым, а
    чёрный список молчал.
    """
    await open_clean_profile(kit, job.source.id)
    await kit.pipeline.reload_resources()
    tools = [*common_tools(kit, job), *seeker_tools(kit, job), *browser_tools(kit, None, None)]
    return await run_seeker(kit, job, await plan_of(tools))
