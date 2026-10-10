"""Способы отклика на вакансию для окна выбора."""

from backend.domain.apply_order import KnownSite, VacancyFacts, Way, World, apply_ways
from backend.domain.contact_keys import is_link
from backend.domain.hosts import owning_host
from backend.models import Vacancy
from backend.repository.aggregators import barred_hosts, list_aggregators
from backend.repository.mail_account import get_mail_account
from backend.repository.vacancy_contacts import contact_values


async def vacancy_ways(session_factory, vacancy_id: int) -> list[Way]:
    """Способы отклика на вакансию по порядку.

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
                            sites=sites, closed_sites=set()))
