"""Отклики агентом: способ за способом, пока один не удался или способы не кончились."""

import asyncio
import logging
from dataclasses import dataclass

from backend.agent.jobs import Applied, ApplyJob, Failed, Finished
from backend.agent.kit import AgentKit, SessionPlan
from backend.agent.prompts.applier import APPLIER_PROMPT, applier_task
from backend.agent.prompts.frame import system_prompt
from backend.agent.sessions import HumanTimeout, LimitExhausted, run_guarded
from backend.agent.tools_applier import applier_tools
from backend.agent.tools_browser import browser_tools
from backend.agent.tools_common import common_tools
from backend.agent.tools_letter import letter_tools
from backend.domain.apply_order import VIA_EMAIL, KnownSite, VacancyFacts, Way, World, apply_ways
from backend.domain.contact_keys import is_link
from backend.domain.hosts import owning_host
from backend.flows.aggregator_round import RoundState
from backend.flows.events import record_vacancy_event
from backend.models import Vacancy, VacancyStatus
from backend.repository.agent_profile import build_agent_profile
from backend.repository.aggregators import barred_hosts, list_aggregators
from backend.repository.mail_account import get_mail_account
from backend.repository.vacancy_brief import describe_vacancy
from backend.repository.vacancy_contacts import contact_values

logger = logging.getLogger(__name__)

_NO_OUTCOME = "агент закончил без итога"


@dataclass(frozen=True)
class ApplyOrder:
    """Что откликать и как: `only` — один выбранный человеком способ."""

    vacancy_id: int
    only: Way | None


async def apply_phase(kit: AgentKit, round_: RoundState, vacancy_ids: list[int]) -> None:
    """Фаза 2 обхода: только вакансии, оставшиеся в New, по одной."""
    total = len(vacancy_ids)
    for number, vacancy_id in enumerate(vacancy_ids, 1):
        title = await _new_title(kit, vacancy_id)
        if title is None:
            continue
        kit.pipeline.emit_progress("apply", f"{title} — отклик", number, total)
        await apply_vacancy(kit, round_, ApplyOrder(vacancy_id, None))


async def apply_vacancy(kit: AgentKit, round_: RoundState, order: ApplyOrder) -> str:
    """Итог для журнала и ленты: `applied`, `closed` или `exhausted`.

    Беда, кроме срока человека, лимита и отмены, — неудача этого способа, а не
    снятие обхода: следующий способ всё ещё может сработать.
    """
    for way in await _ways_for(kit, round_, order):
        try:
            outcome = await _one_way(kit, round_, order, way)
        except (HumanTimeout, LimitExhausted, asyncio.CancelledError):
            raise
        except Exception:
            logger.exception("отклик на вакансию %d способом %s: сбой", order.vacancy_id, way.method)
            await record_vacancy_event(kit.pipeline.session_factory, order.vacancy_id, "apply_failed",
                         {"method": way.method, "reason": "сбой приложения"})
            continue
        if outcome in ("applied", "closed"):
            return outcome
    return "exhausted"


async def _new_title(kit: AgentKit, vacancy_id: int) -> str | None:
    """Название вакансии, если она разобрана и всё ещё в New; иначе пусто —
    фаза её пропускает: у неразобранной нет ни балла, ни приговора."""
    async with kit.pipeline.session_factory() as session:
        vacancy = await session.get(Vacancy, vacancy_id)
    if vacancy is None or not vacancy.is_parsed or vacancy.status is not VacancyStatus.NEW:
        return None
    return vacancy.title or "вакансия"


async def vacancy_ways(session_factory, vacancy_id: int, closed: set[int]) -> list[Way]:
    """Способы отклика на вакансию по порядку — одни для фазы откликов и для окна выбора.

    Сайт из отсева не работает и для откликов: его агрегатор и ссылки на него
    в способы не попадают. Вакансию могли разобрать до того, как сайт занесли
    в отсев, — и откликнуться через него теперь значило бы обойти отметку.
    """
    async with session_factory() as session:
        vacancy = await session.get(Vacancy, vacancy_id)
        if vacancy is None:
            return []
        contacts = await contact_values(session, vacancy_id)
        aggregators = await list_aggregators(session)
        mail_ready = await get_mail_account(session) is not None
        barred = await barred_hosts(session)

    def clear(link: str | None) -> bool:
        return bool(link) and owning_host(link, barred) is None

    sites = [KnownSite(a.id, a.host, a.is_logged_in) for a in aggregators if a.host and clear(a.host)]
    source = next((KnownSite(a.id, a.host) for a in aggregators
                   if a.id == vacancy.source_aggregator_id), None)
    source_url = vacancy.source_url if clear(vacancy.source_url) else None
    contacts = [c for c in contacts if not is_link(c) or clear(c)]
    return apply_ways(VacancyFacts(None, source_url, source, contacts),
                      World(telegram_open=False, mail_ready=mail_ready, agent_ready=True,
                            sites=sites, closed_sites=closed))


async def _ways_for(kit: AgentKit, round_: RoundState, order: ApplyOrder) -> list[Way]:
    if order.only is not None:
        return [order.only]
    return await vacancy_ways(kit.pipeline.session_factory, order.vacancy_id, round_.closed_aggregators)


async def _one_way(kit: AgentKit, round_: RoundState, order: ApplyOrder, way: Way) -> str:
    rs = kit.pipeline.rs
    job = ApplyJob(order.vacancy_id, way.method, way.target, way.aggregator_id,
                   way.aggregator_id or round_.web_search_id, simulated=rs.send_locked, letter_writer=rs.letter_writer)
    plan = await _apply_plan(kit, job)
    if plan is None:
        return "exhausted"
    if way.method != VIA_EMAIL:
        await kit.browser.open_profile(job.profile_id, sending=not job.simulated)
    end = await run_guarded(kit, plan)
    if job.delivery is not None:
        # Сессия снята по сроку, пока сервер почты принимал письмо: исход
        # способа — то, чем кончится отправка, а не пустота. `wait`, а не
        # `gather`: остановка обхода в это время не должна оборвать отправку.
        await asyncio.wait({job.delivery})
    if end.limit_exhausted:
        raise LimitExhausted
    return await _settle_way(kit, round_, job)


async def _apply_plan(kit: AgentKit, job: ApplyJob) -> SessionPlan | None:
    """План откликателя; вакансия удалена между фазами — пусто, способ не пробуется.

    Поиск в сети — для курса валют в анкете и вакансии; у почты браузера нет.
    """
    async with kit.pipeline.session_factory() as session:
        vacancy_text = await describe_vacancy(session, job.vacancy_id)
        if vacancy_text is None:
            return None
        profile_text = await build_agent_profile(session, kit.today)
    tools = [*common_tools(kit, job), *applier_tools(kit, job), *letter_tools(kit, job)]
    if job.method != VIA_EMAIL:
        tools += browser_tools(kit, kit.pipeline.cv_file())
    task = applier_task(job, vacancy_text, profile_text, kit.today)
    return SessionPlan(system_prompt(APPLIER_PROMPT, tools), task, tools, web_search=True)


async def _settle_way(kit: AgentKit, round_: RoundState, job: ApplyJob) -> str:
    """Исход способа; закрытая площадка выпадает из обхода до его конца."""
    outcome = job.outcome
    if isinstance(outcome, Applied):
        return "applied"
    if isinstance(outcome, Finished) and outcome.result == "vacancy_closed":
        await record_vacancy_event(kit.pipeline.session_factory, job.vacancy_id, "vacancy_closed", {"method": job.method, "reason": outcome.reason})
        return "closed"
    if isinstance(outcome, Finished):
        if job.aggregator_id is not None:
            round_.closed_aggregators.add(job.aggregator_id)
        reason = f"площадка закрыла отклик: {outcome.reason}" if outcome.reason else "площадка закрыла отклик"
    else:
        reason = outcome.reason if isinstance(outcome, Failed) else _NO_OUTCOME
    await record_vacancy_event(kit.pipeline.session_factory, job.vacancy_id, "apply_failed", {"method": job.method, "reason": reason})
    return "failed"
