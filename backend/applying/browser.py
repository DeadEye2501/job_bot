"""Браузерный способ: сессия агента на кнопку агрегатора или форму работодателя."""

import asyncio
from pathlib import Path

from backend.agent.confirm import confirming
from backend.agent.jobs import Applied, ApplyJob, Failed, Finished
from backend.agent.kit import AgentKit, SessionPlan
from backend.agent.prompts.applier import APPLIER_PROMPT, applier_task
from backend.agent.prompts.frame import system_prompt
from backend.agent.sessions import WINDOW_CLOSED, run_to_limit
from backend.agent.stops import ResumeMissing
from backend.agent.tools_applier import applier_tools
from backend.agent.tools_browser import browser_tools
from backend.agent.tools_common import common_tools
from backend.agent.tools_letter import letter_tools
from backend.applying.result import GONE, Dropped, Missed, Outcome, SiteClosed, Unfit, WindowClosed
from backend.domain.apply_order import Way
from backend.domain.hosts import normalize_host
from backend.models import Aggregator
from backend.payloads import SeenResume
from backend.repository.aggregator_resumes import chosen_resume, drop_resume
from backend.repository.aggregators import web_search_id
from backend.repository.profile_languages import read_reply_language
from backend.repository.vacancy_brief import describe_vacancy
from backend.repository.vacancy_status import mark_vacancy_unfit

_NO_OUTCOME = "агент закончил без итога"


async def via_browser(kit: AgentKit, vacancy_id: int, way: Way) -> Outcome:
    """Одна сессия агента на способ. Лимит подписки снимает весь прогон: следующий
    способ упёрся бы в него же.

    Выбранного резюме сайт не предложил — его больше нет на сайте: оно
    удаляется из базы (база — зеркало сайта), другое не отмечается, и прогон
    снимается целиком — следующий отклик на этом сайте ушёл бы не тем резюме.

    Окно браузера, закрытое человеком посреди сессии, гасит только её
    (`AgentKit.window_closed`): брошенное ожидание человека прибирается, а сайт
    до конца работы больше не предлагается — у кнопки агрегатора весь агрегатор,
    а не хост ссылки: ссылка бывает на его поддомен.
    """
    rs = kit.pipeline.rs
    async with kit.pipeline.session_factory() as session:
        vacancy_text = await describe_vacancy(session, vacancy_id)
        if vacancy_text is None:
            return GONE
        language = await read_reply_language(session, vacancy_id)
        profile_text = await kit.vacancy_profile_text(session, vacancy_id)
        attached = await kit.reply_resume(session, language)
        site = await session.get(Aggregator, way.aggregator_id) if way.aggregator_id else None
        profile = site.id if site else await web_search_id(session)
        resume = await chosen_resume(session, site.id) if site else None
    job = ApplyJob(vacancy_id, way, profile, simulated=rs.send_locked, letter_writer=rs.letter_writer,
                   language=language, resume=SeenResume(resume.title, resume.url) if resume else None,
                   confirming=confirming(kit))
    closed = asyncio.Event()
    task = applier_task(job, vacancy_text, profile_text, kit.today)
    plan = _apply_plan(kit, job, task, attached.form_file if attached else None, closed)
    kit.window_closed = closed
    try:
        await kit.browser.open_profile(job.profile_id, sending=not job.simulated)
        await run_to_limit(kit, plan)
        # Сессия могла кончиться, так и не заметив закрытого окна: отказ действия
        # агент получает текстом, а событие браузера приходит позже или никогда.
        await kit.browser.notice_closed()
    finally:
        kit.window_closed = None
    shut = (site.host if site else normalize_host(way.target)) if closed.is_set() else None
    if shut is not None:
        kit.gate.forget()
    # «Резюме нет» агент тоже мог сказать, ослепнув без браузера, а цена ошибки
    # здесь — удалённое резюме и снятая работа.
    if shut is None and isinstance(job.outcome, Finished) and job.outcome.result == "resume_missing":
        await kit.written(lambda session: drop_resume(session, site.id, job.resume.url))
        raise ResumeMissing(site.host)
    outcome = _settle(job, way, shut)
    if isinstance(outcome, Unfit):
        await _mark_unfit(kit, vacancy_id, outcome.reason)
    return outcome


async def _mark_unfit(kit: AgentKit, vacancy_id: int, reason: str) -> None:
    """Not Fit пишет исполнитель, как Applied пишет запись отклика: решение о
    статусе принимается там, где узнали исход, а окно слышит о нём той же вестью."""
    await kit.written(lambda session: mark_vacancy_unfit(session, vacancy_id, reason))
    kit.pipeline.fire_vacancies_changed()


def _apply_plan(kit: AgentKit, job: ApplyJob, task: str, resume_file: Path | None,
                closed: asyncio.Event) -> SessionPlan:
    """План откликателя; `resume_file` — файл резюме к форме (`ReplyResume.form_file`)."""
    tools =[*common_tools(kit, job), *applier_tools(kit, job), *letter_tools(kit, job),
             *browser_tools(kit, resume_file, kit.pipeline.photo_file(), job if job.confirming else None)]
    return SessionPlan(system_prompt(APPLIER_PROMPT, tools), task, tools, web_search=False, cut=closed)


def _settle(job: ApplyJob, way: Way, shut: str | None) -> Outcome:
    """Исход способа; закрытая площадка — урок, её кнопка до конца прогона не
    предлагается. `shut` — хост сайта, чьё окно закрыл человек; пусто — окно
    не закрывали. Закрытое окно уступает только ушедшему отклику и «Закончить»:
    прочий итог агент мог поставить, уже ослепнув без браузера."""
    outcome = job.outcome
    if isinstance(outcome, Applied):
        return "applied"
    if isinstance(outcome, Dropped):
        return outcome
    if shut is not None:
        return Missed(WINDOW_CLOSED, WindowClosed(shut))
    if isinstance(outcome, Finished) and outcome.result == "vacancy_closed":
        return Missed("вакансия закрыта на сайте")
    if isinstance(outcome, Finished) and outcome.result == "not_fit":
        return Unfit(outcome.reason)
    if isinstance(outcome, Finished):
        reason = f"площадка закрыла отклик: {outcome.reason}" if outcome.reason else "площадка закрыла отклик"
        lesson = SiteClosed(way.aggregator_id) if way.aggregator_id is not None else None
        return Missed(reason, lesson)
    return Missed(outcome.reason if isinstance(outcome, Failed) else _NO_OUTCOME)
