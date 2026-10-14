"""Перечень резюме на сайте агрегатора: агент перечисляет резюме человека, база приводится к увиденному.

От входа (`aggregator_login`) отличается тем, что работает агент, а не человек:
браузер открыт в профиле сайта как обычно, и звать человека агенту можно —
по кнопке ему встретятся вход заново и капча.
"""

import logging

from backend.agent.jobs import Finished, ScanJob, Source
from backend.agent.kit import AgentKit, SessionPlan
from backend.agent.prompts.frame import system_prompt
from backend.agent.prompts.scan import SCAN_PROMPT, scan_task
from backend.agent.sessions import run_to_limit
from backend.agent.tools_browser import browser_tools
from backend.agent.tools_common import common_tools
from backend.agent.tools_scan import scan_tools
from backend.models import Aggregator

logger = logging.getLogger(__name__)


async def scan(kit: AgentKit, source: Source) -> str:
    """Перечень резюме сайта. Ответ — `ok`, когда список дошёл до базы;
    `not_logged_in`, когда агент нашёл сайт без входа; иначе `error` с записью
    в журнал. Без `ok` список остаётся прежним."""
    await kit.browser.open_profile(source.id)
    job = ScanJob(source)
    tools = [*common_tools(kit, job), *scan_tools(kit, job), *browser_tools(kit, None, None)]
    plan = SessionPlan(system_prompt(SCAN_PROMPT, tools), scan_task(source.host), tools,
                       web_search=False)
    end = await run_to_limit(kit, plan)
    if job.reported:
        return "ok"
    async with kit.pipeline.session_factory() as session:
        if not (await session.get(Aggregator, source.id)).is_logged_in:
            return "not_logged_in"
    reason = job.outcome.reason if isinstance(job.outcome, Finished) else end.detail
    logger.warning("перечень резюме %s: списка нет — %s", source.name, reason or "агент молчал")
    return "error"
