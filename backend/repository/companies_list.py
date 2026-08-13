"""Перечень компаний со счётчиками."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Company, Vacancy
from backend.payloads import CompanyWithCount, str_list

from backend.repository.blacklist_marks import active_blacklist_values
from backend.repository.companies_card import company_blacklist_candidates
from backend.repository.paging import slice_page
from backend.repository.search import matches_search


def _companies_with_counts_query():
    """Компании со счётчиком вакансий, плодовитые сверху.

    Разрешитель по имени не украшение: у компаний без вакансий счёт один и
    тот же, и без него порядок списка менялся бы от прогона к прогону.
    """
    return (
        select(Company, func.count(Vacancy.id).label("cnt"))
        .outerjoin(Vacancy, Vacancy.company_id == Company.id)
        .group_by(Company.id)
        .order_by(func.count(Vacancy.id).desc(), Company.name.asc())
    )


async def list_companies_with_counts(
    session: AsyncSession,
    search: str | None = None,
    *,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[list[CompanyWithCount], bool]:
    """Страница компаний со счётом вакансий и отметкой отсева, и есть ли за ней ещё.

    ``search`` is matched against name, aliases and website Python-side —
    see :func:`backend.repository.search.matches_search`. Страница отрезается
    после отбора, и признак продолжения приходит оттуда же —
    `paging.slice_page`.
    """
    rows = (await session.execute(_companies_with_counts_query())).all()
    rows = [
        (c, cnt)
        for c, cnt in rows
        if matches_search(search, c.name, c.website, *str_list(c.aliases))
    ]

    rows, has_more = slice_page(rows, limit, offset)

    bl_values = await active_blacklist_values(session, "company")

    return [
        CompanyWithCount(
            company=c,
            vacancy_count=int(cnt or 0),
            is_blacklisted=any(v in bl_values for v in company_blacklist_candidates(c)),
        )
        for c, cnt in rows
    ], has_more
