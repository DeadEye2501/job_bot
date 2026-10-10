"""Фаза откликов обхода: способ за способом, пока один не удался или способы не кончились."""

from dataclasses import dataclass

from backend.agent.kit import AgentKit
from backend.applying.result import SiteClosed
from backend.applying.run import apply_chosen
from backend.domain.apply_order import KnownSite, VacancyFacts, Way, World, apply_ways
from backend.domain.contact_keys import is_link
from backend.domain.hosts import owning_host
from backend.flows.aggregator_round import RoundState
from backend.models import Vacancy, VacancyStatus
from backend.repository.aggregators import barred_hosts, list_aggregators
from backend.repository.mail_account import get_mail_account
from backend.repository.vacancy_contacts import contact_values


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
    """Итог: `applied` или `exhausted`. Способ пробует исполнитель откликателя;
    закрытая площадка выпадает из обхода до его конца."""
    for way in await _ways_for(kit, round_, order):
        outcome = await apply_chosen(kit, order.vacancy_id, way)
        if outcome == "applied":
            return "applied"
        if isinstance(outcome.lesson, SiteClosed):
            round_.closed_aggregators.add(outcome.lesson.site_id)
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
