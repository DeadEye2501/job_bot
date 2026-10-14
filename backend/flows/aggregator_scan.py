"""Перечень резюме на сайте агрегатора: агент перечисляет резюме человека, база приводится к увиденному.

От входа (`aggregator_login`) отличается тем, что работает агент, а не человек:
браузер открыт в профиле сайта как обычно, и звать человека агенту можно —
по кнопке ему встретятся вход заново и капча.
"""

import logging

from adapters.claude_code_agent import AgentEnd
from backend.agent.jobs import Finished, ScanJob, Source
from backend.agent.kit import AgentKit, SessionPlan
from backend.agent.prompts.frame import system_prompt
from backend.agent.prompts.scan import SCAN_PROMPT, scan_task
from backend.agent.sessions import run_to_limit
from backend.agent.tools_browser import browser_tools
from backend.agent.tools_common import common_tools
from backend.agent.tools_scan import scan_tools
from backend.repository.aggregators import is_logged_in

logger = logging.getLogger(__name__)


async def run_on_site(kit: AgentKit, job, prompt: str, task: str, *own_tools) -> AgentEnd:
    """Сессия агента на сайте источника — у входа и у перечня резюме: общие
    инструменты задачи, её собственные и браузер; веб-поиск сайту не нужен."""
    tools = [*common_tools(kit, job), *own_tools, *browser_tools(kit, None, None)]
    plan = SessionPlan(system_prompt(prompt, tools), task, tools, web_search=False)
    return await run_to_limit(kit, plan)


async def scan(kit: AgentKit, source: Source) -> str:
    """Перечень резюме сайта. Ответ — `ok`, когда список дошёл до базы;
    `not_logged_in`, когда агент нашёл сайт без входа; иначе `error` с записью
    в журнал. Без `ok` список остаётся прежним."""
    await kit.browser.open_profile(source.id)
    job = ScanJob(source)
    end = await run_on_site(kit, job, SCAN_PROMPT, scan_task(source.host), *scan_tools(kit, job))
    if job.reported:
        return "ok"
    async with kit.pipeline.session_factory() as session:
        if not await is_logged_in(session, source.id):
            return "not_logged_in"
    reason = job.outcome.reason if isinstance(job.outcome, Finished) else end.detail
    logger.warning("перечень резюме %s: списка нет — %s", source.name, reason or "агент молчал")
    return "error"
