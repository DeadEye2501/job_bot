"""Перечень компаний со счётчиками."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Company, Vacancy
from backend.payloads import CompanyWithCount

from backend.repository.blacklist_marks import active_blacklist_values
from backend.repository.companies_card import company_blacklist_candidates
from backend.repository.search import matches_search


def _spellings(company: Company) -> list:
    """Написания компании, годные к перебору.

    Колонка JSON, и что в ней лежит, код не обещает. Не-список пришлось бы
    разворачивать звёздочкой, а это уронило бы весь перечень компаний — даже
    когда искать не просили."""
    return company.aliases if isinstance(company.aliases, list) else []


async def list_companies_with_counts(
    session: AsyncSession,
    search: str | None = None,
    *,
    limit: int | None = None,
    offset: int = 0,
) -> list[CompanyWithCount]:
    """All companies with their vacancy count + blacklist status.

    ``search`` is matched against name, aliases and website Python-side —
    see :func:`backend.repository.search.matches_search`.
    ``limit``/``offset`` slice the result *after* the search filter so the
    Contacts/Companies pane can implement infinite scroll.
    """
    base = (
        select(Company, func.count(Vacancy.id).label("cnt"))
        .outerjoin(Vacancy, Vacancy.company_id == Company.id)
        .group_by(Company.id)
        .order_by(func.count(Vacancy.id).desc(), Company.name.asc())
    )
    rows = (await session.execute(base)).all()

    rows = [
        (c, cnt)
        for c, cnt in rows
        if matches_search(search, c.name, c.website, *_spellings(c))
    ]

    if limit is not None:
        rows = rows[offset : offset + limit]

    bl_values = await active_blacklist_values(session, "company")

    return [
        CompanyWithCount(
            company=c,
            vacancy_count=int(cnt or 0),
            is_blacklisted=any(v in bl_values for v in company_blacklist_candidates(c)),
        )
        for c, cnt in rows
    ]
