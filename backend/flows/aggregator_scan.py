"""Перечень резюме на сайте агрегатора: агент перечисляет резюме человека, база приводится к увиденному.

От входа (`aggregator_login`) отличается тем, что работает агент, а не человек:
браузер открыт в профиле сайта как обычно, и звать человека агенту можно —
по кнопке ему встретятся вход заново и капча.
"""

import logging

from backend.agent.jobs import Finished, ScanJob, Source
from backend.agent.kit import AgentKit
from backend.agent.prompts.scan import SCAN_PROMPT, scan_task
from backend.agent.sessions import run_on_site
from backend.agent.tools_browser import browser_tools
from backend.agent.tools_scan import scan_tools
from backend.repository.aggregators import is_logged_in

logger = logging.getLogger(__name__)


async def scan(kit: AgentKit, source: Source) -> str:
    """Перечень резюме сайта. Ответ — `ok`, когда список дошёл до базы;
    `not_logged_in`, когда агент нашёл сайт без входа; иначе `error` с записью
    в журнал. Без `ok` список остаётся прежним."""
    await kit.browser.open_profile(source.id)
    job = ScanJob(source)
    end = await run_on_site(kit, job, SCAN_PROMPT, scan_task(source.host),
                            *scan_tools(kit, job), *browser_tools(kit, None, None))
    if job.reported:
        return "ok"
    async with kit.pipeline.session_factory() as session:
        if not await is_logged_in(session, source.id):
            return "not_logged_in"
    reason = job.outcome.reason if isinstance(job.outcome, Finished) else end.detail
    logger.warning("перечень резюме %s: списка нет — %s", source.name, reason or "агент молчал")
    return "error"
