"""Вход на сайт агрегатора: человек входит в обычном браузере, агент проверяет вход.

Подтверждённый вход сразу продолжается перечнем резюме (`aggregator_scan`):
вход и есть тот момент, когда список на сайте впервые можно увидеть.
"""

from backend.agent.human_gate import LIMIT_SEC
from backend.agent.jobs import LoginJob, Source
from backend.agent.kit import AgentKit
from backend.agent.prompts.login import LOGIN_PROMPT, login_task
from backend.agent.tools_browser import browser_tools
from backend.agent.sessions import run_on_site
from backend.flows.aggregator_scan import scan
from backend.repository.aggregators import is_logged_in


async def log_in(kit: AgentKit, source: Source) -> str:
    """Обычный браузер на главной; человек входит и закрывает окно; агент отмечает
    вход, а подтвердив его — перечисляет резюме на сайте (`aggregator_scan`).

    Ответ — `ok`, `not_logged_in` (агент входа не нашёл) или `login_timeout`
    (окно не закрыто за час). Судит отметка в базе, а не конец сессии: сессия
    кончается и тогда, когда входа нет.
    """
    # Вход — то же ожидание человека, что капча: срок у них один.
    if not await kit.browser.let_person_in(source.id, f"https://{source.host}/", LIMIT_SEC):
        return "login_timeout"
    await run_on_site(kit, LoginJob(source), LOGIN_PROMPT, login_task(source.host),
                      *browser_tools(kit, None, None))
    if not await kit.read(lambda session: is_logged_in(session, source.id)):
        return "not_logged_in"
    # Вход подтверждён — ответ входа уже `ok`: неудачный перечень резюме пишет
    # свою причину в журнал, а вход от неё не становится несостоявшимся.
    # Остановки работы — истёкшее ожидание человека, лимит — идут насквозь,
    # как в любой работе агента: человек должен узнать, что его ждали.
    await scan(kit, source)
    return "ok"
