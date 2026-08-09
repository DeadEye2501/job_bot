"""Перечень компаний со счётчиками."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Blacklist, Company, Vacancy
from backend.payloads import CompanyWithCount

from backend.repository.companies_card import company_blacklist_candidates


async def list_companies_with_counts(
    session: AsyncSession,
    search: str | None = None,
    *,
    limit: int | None = None,
    offset: int = 0,
) -> list[CompanyWithCount]:
    """All companies with their vacancy count + blacklist status.

    ``search`` is matched against name, aliases, and website using
    Python-side ``str.casefold()`` (SQLite's ``lower()`` is ASCII-only).
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

    if search:
        q = search.strip().casefold()
        if q:
            def matches(co: Company) -> bool:
                if q in co.name.casefold():
                    return True
                if co.website and q in co.website.casefold():
                    return True
                for alias in (co.aliases or []):
                    if isinstance(alias, str) and q in alias.casefold():
                        return True
                return False
            rows = [(c, cnt) for c, cnt in rows if matches(c)]

    if limit is not None:
        rows = rows[offset : offset + limit]

    bl_values = set(
        (
            await session.scalars(
                select(Blacklist.value).where(
                    Blacklist.kind == "company",
                    Blacklist.active.is_(True),
                )
            )
        ).all()
    )

    return [
        CompanyWithCount(
            company=c,
            vacancy_count=int(cnt or 0),
            is_blacklisted=any(v in bl_values for v in company_blacklist_candidates(c)),
        )
        for c, cnt in rows
    ]
