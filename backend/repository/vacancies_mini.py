"""Короткие списки вакансий для карточек других предметов."""

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Vacancy, VacancyStatus

# Channel mini-list sort order — UI requirement: hottest funnel statuses
# first (Offer / In Progress / Invitation / Test / Answered / Applied / New),
# then unresolved cold (Scam / Ghosting / Decline), then NotFit at the
# bottom. Secondary sort внутри одного статуса — по дате появления вакансии
# (posted_at если есть, иначе created_at), новые сверху.
#
# Ключи — .value-строки, а не enum-члены: при `case(dict, value=col)` SA
# биндит ключи как литералы БЕЗ прогона через Enum-type processor колонки,
# и aiosqlite падает с `type 'VacancyStatus' is not supported`. Падение
# проглатывалось в `_dispatch` как _err, и мини-список рендерил «нет
# вакансий», хотя badge/funnel показывали реальный count.
_CHANNEL_VAC_STATUS_RANK: dict[str, int] = {
    VacancyStatus.OFFER.value: 1,
    VacancyStatus.IN_PROGRESS.value: 2,
    VacancyStatus.INVITATION.value: 3,
    VacancyStatus.TEST.value: 4,
    VacancyStatus.ANSWERED.value: 5,
    VacancyStatus.APPLIED.value: 6,
    VacancyStatus.NEW.value: 7,
    VacancyStatus.SCAM.value: 8,
    VacancyStatus.GHOSTING.value: 9,
    VacancyStatus.DECLINE.value: 10,
    VacancyStatus.NOT_FIT.value: 11,
}


async def list_vacancies_for_hr(
    session: AsyncSession,
    hr_id: int,
) -> list[Vacancy]:
    """All parsed vacancies for an HR, newest-first. Powers the «список
    вакансий» mini-list in the Contacts/HR detail pane.

    Skips ``is_parsed=False`` rows so half-built (crash-recovered) vacancies
    don't surface in the chip — the same gate the main vacancies list uses.
    """
    rows = (
        await session.scalars(
            select(Vacancy)
            .where(Vacancy.hr_id == hr_id, Vacancy.is_parsed.is_(True))
            .order_by(Vacancy.created_at.desc(), Vacancy.id.desc())
        )
    ).all()
    return list(rows)


async def list_vacancies_for_company(
    session: AsyncSession, company_id: int
) -> list[Vacancy]:
    """All parsed vacancies linked to this company, newest-first."""
    rows = (
        await session.scalars(
            select(Vacancy)
            .where(Vacancy.company_id == company_id, Vacancy.is_parsed.is_(True))
            .order_by(Vacancy.created_at.desc(), Vacancy.id.desc())
        )
    ).all()
    return list(rows)


async def list_vacancies_for_channel(
    session: AsyncSession,
    channel_id: int,
    *,
    limit: int = 50,
    offset: int = 0,
) -> list[Vacancy]:
    """Все вакансии из канала, sorted by status priority then by recency.
    Pagination via limit/offset — каналы могут накапливать тысячи вакансий,
    мини-список в detail-pane грузит их пачками.

    is_parsed-фильтр НЕ применяем: badge канала и stats-блок считают все
    вакансии (без этого фильтра), и фильтрация мини-списка по is_parsed=True
    создавала рассинхрон — count=14, stats=14, мини-список пустой. Это
    случается в том числе у пользователей со старыми данными до миграции
    df83674 (`is_parsed` появился позже, существующие parsed-ряды получили
    дефолт False, и `recover_orphan_vacancies` не всегда успевает их
    восстановить — например, без активного бота). Половинно-построенные
    ряды (только raw_text) рендерятся как «— без названия —» через
    существующий fallback в UI.
    """
    status_rank = case(
        _CHANNEL_VAC_STATUS_RANK,
        value=Vacancy.status,
        else_=99,
    )
    activity = func.coalesce(Vacancy.posted_at, Vacancy.created_at)
    rows = (
        await session.scalars(
            select(Vacancy)
            .where(Vacancy.source_channel_id == channel_id)
            .order_by(status_rank.asc(), activity.desc(), Vacancy.id.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return list(rows)
