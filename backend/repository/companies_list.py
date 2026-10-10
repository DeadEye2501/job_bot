"""Перечень компаний со счётчиками."""

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Company, Vacancy
from backend.payloads import CompanyWithCount
from backend.incoming import str_list

from backend.repository.companies_card import COMPANY_BLACKLIST
from backend.repository.paging import searched_page
from backend.repository.search import matches_search
from backend.repository.vacancies_common import with_vacancy_counts


async def list_companies_with_counts(
    session: AsyncSession,
    search: str | None = None,
    *,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[list[CompanyWithCount], bool]:
    """Страница компаний со счётом вакансий и отметкой отсева, и есть ли за ней ещё.

    Ищут по имени, написаниям и сайту — см.
    :func:`backend.repository.search.matches_search`. Страница отрезается
    после отбора, и признак продолжения приходит оттуда же —
    `paging.searched_page`.
    """
    rows = (
        await session.execute(with_vacancy_counts(Company, Vacancy.company_id, Company.name))
    ).all()
    rows, has_more = searched_page(
        rows,
        lambda row: matches_search(
            search, row[0].name, row[0].website, *str_list(row[0].aliases)
        ),
        limit,
        offset,
    )

    bl_values = await COMPANY_BLACKLIST.marked(session)

    return [
        CompanyWithCount(
            company=c,
            vacancy_count=int(cnt or 0),
            is_blacklisted=COMPANY_BLACKLIST.among(c, bl_values),
        )
        for c, cnt in rows
    ], has_more
