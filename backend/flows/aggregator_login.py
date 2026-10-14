"""Вход на сайт агрегатора: человек входит в видимом браузере, агент проверяет вход.

Подтверждённый вход сразу продолжается перечнем резюме (`aggregator_scan`):
вход и есть тот момент, когда список на сайте впервые можно увидеть.
"""

from backend.agent.human_gate import LIMIT_SEC
from backend.agent.jobs import LoginJob, Source
from backend.agent.kit import AgentKit, SessionPlan
from backend.agent.prompts.frame import system_prompt
from backend.agent.prompts.login import LOGIN_PROMPT, login_task
from backend.agent.sessions import run_to_limit
from backend.agent.tools_browser import browser_tools
from backend.agent.tools_common import common_tools
from backend.flows.aggregator_scan import scan
from backend.models import Aggregator


async def log_in(kit: AgentKit, source: Source) -> str:
    """Видимый браузер на главной; человек входит и закрывает окно; агент отмечает
    вход, а подтвердив его — перечисляет резюме на сайте (`aggregator_scan`).

    Ответ — `ok`, `not_logged_in` (агент входа не нашёл) или `login_timeout`
    (окно не закрыто за час). Судит отметка в базе, а не конец сессии: сессия
    кончается и тогда, когда входа нет.
    """
    await kit.browser.open_profile(source.id, as_person=True)
    await kit.browser.show()
    await (await kit.browser.page()).goto(f"https://{source.host}/")
    # Вход — то же ожидание человека, что капча: срок у них один.
    if not await kit.browser.wait_closed(LIMIT_SEC):
        return "login_timeout"
    job = LoginJob(source)
    tools = [*common_tools(kit, job), *browser_tools(kit, None, None)]
    plan = SessionPlan(system_prompt(LOGIN_PROMPT, tools), login_task(source.host), tools,
                       web_search=False)
    await run_to_limit(kit, plan)
    async with kit.pipeline.session_factory() as session:
        row = await session.get(Aggregator, source.id)
    if row is None or not row.is_logged_in:
        return "not_logged_in"
    # Вход подтверждён — ответ входа уже `ok`: неудачный перечень резюме пишет
    # свою причину в журнал, а вход от неё не становится несостоявшимся.
    # Остановки работы — истёкшее ожидание человека, лимит — идут насквозь,
    # как в любой работе агента: человек должен узнать, что его ждали.
    await scan(kit, source)
    return "ok"
