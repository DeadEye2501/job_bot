"""Общие инструменты агента: анкета, итог сессии, зов человека, отметка входа, неудача способа."""

from collections.abc import Callable

from backend.agent.jobs import Applied, ApplyJob, Failed, Finished, LoginJob, SeekJob
from backend.agent.kit import AgentKit
from backend.domain.hosts import normalize_host
from backend.repository.agent_profile import build_agent_profile
from backend.models import ApplicationVia
from backend.repository.aggregators import set_logged_in

_ALREADY_APPLIED = (
    "Отклик уже записан, итог не меняется: второй отклик ушёл бы тому же "
    "работодателю другим способом. Заверши работу."
)

_RESULTS = {
    LoginJob: {"done"},
    SeekJob: {"done", "failed"},
    ApplyJob: {"vacancy_closed", "platform_closed"},
}


def common_tools(kit: AgentKit, job) -> list[Callable]:
    """Инструменты, привязанные к задаче сессии: за её пределы они не выходят.

    Подписи — с аннотациями всегда: по ним MCP строит схему инструмента для агента.
    """

    async def profile() -> str:
        """Анкета человека целиком, со стажем общим и по навыкам."""
        async with kit.pipeline.session_factory() as session:
            return await build_agent_profile(session, kit.today) or "Анкета не заполнена."

    async def finish(result: str, reason: str = "") -> str:
        """Итог сессии. Искатель: done или failed. Откликатель: vacancy_closed или platform_closed. Проверка входа: done."""
        if result not in _RESULTS[type(job)]:
            return f"Итога «{result}» у этой задачи не бывает: {', '.join(sorted(_RESULTS[type(job)]))}."
        if isinstance(job.outcome, Applied):
            return _ALREADY_APPLIED
        job.outcome = Finished(result, reason)
        return "Итог записан, работа окончена."

    tools = [profile, finish, _need_human(kit, job)]
    aggregator_id = _login_target(job)
    if aggregator_id is not None:
        tools.append(_report_login(kit, aggregator_id))
    if isinstance(job, ApplyJob):
        tools.append(_report_failure(job))
    return tools


def _login_target(job) -> int | None:
    if isinstance(job, (LoginJob, SeekJob)):
        return job.source.id if job.source.host is not None else None
    return job.aggregator_id if job.method == ApplicationVia.AGGREGATOR.value else None


def _need_human(kit: AgentKit, job) -> Callable:
    async def need_human(kind: str) -> str:
        """Нужен человек: kind — captcha или login. Вызов держится, пока человек не нажмёт «Готово». Ответ «срок вышел» — заверши работу."""
        if kind not in ("captcha", "login"):
            return "kind — captcha или login."
        return await kit.gate.wait(kind, _host_of(job) or "сайт", kit.browser)

    return need_human


def _host_of(job) -> str | None:
    """Сайт, на котором нужен человек: источник поиска или адрес способа отклика."""
    if isinstance(job, ApplyJob):
        return normalize_host(job.target) or None
    return job.source.host


def _report_login(kit: AgentKit, aggregator_id: int) -> Callable:
    async def report_login(logged_in: bool) -> str:
        """Вошёл ли человек на сайт: true — вошёл, false — нет."""
        async with kit.pipeline.session_factory() as session:
            async with session.begin():
                await set_logged_in(session, aggregator_id, logged_in)
        return "Отметка входа записана."

    return report_login


def _report_failure(job: ApplyJob) -> Callable:
    async def report_failure(reason: str) -> str:
        """Отклик этим способом не удался; причина — коротко, по-русски."""
        if isinstance(job.outcome, Applied):
            return _ALREADY_APPLIED
        job.outcome = Failed(reason)
        return "Неудача записана. Приложение попробует другой способ."

    return report_failure
