"""Факты для выбора способа: что известно о вакансии и что сейчас доступно."""

import time

from sqlalchemy.ext.asyncio import AsyncSession

from backend.agent.availability import current_refusal
from backend.agent.kit import AgentKit
from backend.applying.result import Lesson, TelegramClosed
from backend.domain.apply_order import KnownSite, VacancyFacts, Way, World, apply_ways
from backend.models import HR, Aggregator, Vacancy
from backend.repository.aggregators import list_aggregators
from backend.repository.mail_account import get_mail_account
from backend.repository.vacancy_contacts import contact_values


async def read_world(kit: AgentKit) -> World:
    """Что доступно прямо сейчас; закрытых до конца прогона сайтов ещё нет."""
    rs = kit.pipeline.rs
    async with kit.pipeline.session_factory() as session:
        mail_ready = await get_mail_account(session) is not None
        aggregators = await list_aggregators(session)
    return World(
        telegram_open=rs.flood_wait_until_ts <= time.time(),
        mail_ready=mail_ready,
        agent_ready=current_refusal(rs.chat) is None,
        sites=[KnownSite(a.id, a.host, a.is_logged_in) for a in aggregators],
        closed_sites=set(),
    )


async def vacancy_facts(session: AsyncSession, vacancy_id: int) -> VacancyFacts | None:
    """Факты вакансии одной сессией; удалённая — пусто."""
    vacancy = await session.get(Vacancy, vacancy_id)
    if vacancy is None:
        return None
    hr = await session.get(HR, vacancy.hr_id) if vacancy.hr_id else None
    site = (await session.get(Aggregator, vacancy.source_aggregator_id)
            if vacancy.source_aggregator_id else None)
    return VacancyFacts(
        hr_handle=_handle(hr),
        source_url=vacancy.source_url,
        source_site=KnownSite(site.id, site.host) if site else None,
        contacts=await contact_values(session, vacancy_id),
    )


def _handle(hr: HR | None) -> str | None:
    """Адрес HR в Telegram словом окна: `@ник`, иначе номер; без адреса — не способ."""
    if hr is None:
        return None
    if hr.telegram_username:
        return f"@{hr.telegram_username}"
    return str(hr.telegram_user_id) if hr.telegram_user_id else None


async def ways_in(kit: AgentKit, world: World, vacancy_id: int) -> list[Way]:
    """Способы вакансии в этом мире; удалённая — пустой перечень."""
    async with kit.pipeline.session_factory() as session:
        facts = await vacancy_facts(session, vacancy_id)
    return [] if facts is None else apply_ways(facts, world)


def learn(world: World, lesson: Lesson) -> None:
    """Доучить мир тем, что узнал исполнитель."""
    if isinstance(lesson, TelegramClosed):
        world.telegram_open = False
    else:
        world.closed_sites.add(lesson.site_id)
