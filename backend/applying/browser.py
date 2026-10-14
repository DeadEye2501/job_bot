"""Браузерный способ: сессия агента на кнопку агрегатора или форму работодателя."""

from backend.agent.confirm import confirming
from backend.agent.jobs import Applied, ApplyJob, Failed, Finished
from backend.agent.kit import AgentKit, SessionPlan
from backend.agent.prompts.applier import APPLIER_PROMPT, applier_task
from backend.agent.prompts.frame import system_prompt
from backend.agent.sessions import run_guarded
from backend.agent.stops import LimitExhausted
from backend.agent.tools_applier import applier_tools
from backend.agent.tools_browser import browser_tools
from backend.agent.tools_common import common_tools
from backend.agent.tools_letter import letter_tools
from backend.applying.result import GONE, Dropped, Missed, Outcome, SiteClosed, Unfit
from backend.domain.apply_order import Way
from backend.repository.agent_profile import build_agent_profile
from backend.repository.aggregators import web_search_id
from backend.repository.vacancy_brief import describe_vacancy
from backend.repository.vacancy_status import mark_vacancy_unfit

_NO_OUTCOME = "агент закончил без итога"


async def via_browser(kit: AgentKit, vacancy_id: int, way: Way) -> Outcome:
    """Одна сессия агента на способ. Лимит подписки снимает весь прогон: следующий
    способ упёрся бы в него же."""
    rs = kit.pipeline.rs
    async with kit.pipeline.session_factory() as session:
        profile = way.aggregator_id or await web_search_id(session)
    job = ApplyJob(vacancy_id, way, profile, simulated=rs.send_locked, letter_writer=rs.letter_writer,
                   confirming=confirming(kit))
    plan = await _apply_plan(kit, job)
    if plan is None:
        return GONE
    await kit.browser.open_profile(job.profile_id, sending=not job.simulated)
    end = await run_guarded(kit, plan)
    if end.limit_exhausted:
        raise LimitExhausted
    outcome = _settle(job, way)
    if isinstance(outcome, Unfit):
        await _mark_unfit(kit, vacancy_id, outcome.reason)
    return outcome


async def _mark_unfit(kit: AgentKit, vacancy_id: int, reason: str) -> None:
    """Not Fit пишет исполнитель, как Applied пишет запись отклика: решение о
    статусе принимается там, где узнали исход, а окно слышит о нём той же вестью."""
    await kit.written(lambda session: mark_vacancy_unfit(session, vacancy_id, reason))
    kit.pipeline.fire_vacancies_changed()


async def _apply_plan(kit: AgentKit, job: ApplyJob) -> SessionPlan | None:
    """План откликателя; удалённая вакансия — пусто.

    Поиск в сети — для курса валют в анкете и вакансии.
    """
    async with kit.pipeline.session_factory() as session:
        vacancy_text = await describe_vacancy(session, job.vacancy_id)
        if vacancy_text is None:
            return None
        photo = kit.pipeline.photo_file()
        profile_text = await build_agent_profile(session, kit.today, photo is not None)
    tools = [*common_tools(kit, job), *applier_tools(kit, job), *letter_tools(kit, job),
             *browser_tools(kit, kit.pipeline.cv_file(), photo, job if job.confirming else None)]
    task = applier_task(job, vacancy_text, profile_text, kit.today)
    return SessionPlan(system_prompt(APPLIER_PROMPT, tools), task, tools, web_search=True)


def _settle(job: ApplyJob, way: Way) -> Outcome:
    """Исход способа; закрытая площадка — урок, её кнопка до конца прогона не предлагается."""
    outcome = job.outcome
    if isinstance(outcome, Applied):
        return "applied"
    if isinstance(outcome, Dropped):
        return outcome
    if isinstance(outcome, Finished) and outcome.result == "vacancy_closed":
        return Missed("вакансия закрыта на сайте")
    if isinstance(outcome, Finished) and outcome.result == "not_fit":
        return Unfit(outcome.reason)
    if isinstance(outcome, Finished):
        reason = f"площадка закрыла отклик: {outcome.reason}" if outcome.reason else "площадка закрыла отклик"
        lesson = SiteClosed(way.aggregator_id) if way.aggregator_id is not None else None
        return Missed(reason, lesson)
    return Missed(outcome.reason if isinstance(outcome, Failed) else _NO_OUTCOME)
