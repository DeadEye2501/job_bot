"""Ведение записей о компаниях."""

import logging

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Blacklist, Company, Vacancy
from backend.payloads import CompanyDetail

from backend.repository.hr_card import _concat_notes

logger = logging.getLogger(__name__)


async def create_company(
    session: AsyncSession,
    *,
    name: str,
    website: str | None = None,
    aliases: list[str] | None = None,
    notes: str | None = None,
) -> Company:
    """Insert a new Company row. Raises if name is empty.

    Unique constraint on ``company.name`` will surface as IntegrityError if
    the user tries to create a duplicate; caller can convert that into a
    user-facing message.
    """
    normalized = (name or "").strip()
    if not normalized:
        raise ValueError("create_company: name is required")
    company = Company(
        name=normalized,
        aliases=list(aliases or []),
        website=(website or None),
        notes=(notes or None),
    )
    session.add(company)
    await session.flush()
    logger.info(
        "Created company id=%d name=%r website=%s",
        company.id,
        normalized,
        website,
    )
    return company


def company_blacklist_candidates(co: Company) -> list[str]:
    """Possible blacklist `value` strings that should match this company.

    Just the company name — no other identifiers exist (no @username
    equivalent for companies). Returned as a list to mirror the HR helper
    so callers can use the same `value.in_(candidates)` shape.
    """
    return [co.name] if co.name else []


def company_blacklist_preferred_value(co: Company) -> str | None:
    return co.name or None


async def _company_blacklist_value(
    session: AsyncSession, co: Company
) -> str | None:
    candidates = company_blacklist_candidates(co)
    if not candidates:
        return None
    row = (
        await session.scalars(
            select(Blacklist)
            .where(
                Blacklist.kind == "company",
                Blacklist.value.in_(candidates),
                Blacklist.active.is_(True),
            )
            .order_by(Blacklist.id.asc())
            .limit(1)
        )
    ).first()
    return row.value if row else None


async def get_company_detail(
    session: AsyncSession, company_id: int
) -> "CompanyDetail | None":
    """Detail payload for the Contacts/Companies pane (06): company row +
    vacancy count + distinct HR count + blacklist status.
    """
    co = await session.get(Company, company_id)
    if co is None:
        return None
    vacancy_count = int(
        await session.scalar(
            select(func.count(Vacancy.id)).where(Vacancy.company_id == company_id)
        )
        or 0
    )
    hr_count = int(
        await session.scalar(
            select(func.count(func.distinct(Vacancy.hr_id))).where(
                Vacancy.company_id == company_id,
                Vacancy.hr_id.is_not(None),
            )
        )
        or 0
    )
    blacklist_value = await _company_blacklist_value(session, co)
    return CompanyDetail(
        company=co,
        vacancy_count=vacancy_count,
        hr_count=hr_count,
        blacklist_value=blacklist_value,
    )


_COMPANY_FIELD_UNSET = object()


async def update_company_fields(
    session: AsyncSession,
    company_id: int,
    *,
    name=_COMPANY_FIELD_UNSET,
    website=_COMPANY_FIELD_UNSET,
    aliases=_COMPANY_FIELD_UNSET,
    notes=_COMPANY_FIELD_UNSET,
) -> bool:
    """Patch one or more Company columns. Sentinel-default unset = leave
    unchanged. Returns False if the company id isn't found.
    """
    co = await session.get(Company, company_id)
    if co is None:
        return False
    changed = []
    if name is not _COMPANY_FIELD_UNSET:
        cleaned = (str(name).strip() if name is not None else "")
        if not cleaned:
            return False  # company name is required (UNIQUE NOT NULL)
        co.name = cleaned
        changed.append("name")
    if website is not _COMPANY_FIELD_UNSET:
        co.website = (
            (str(website).strip() or None) if website is not None else None
        )
        changed.append("website")
    if aliases is not _COMPANY_FIELD_UNSET:
        # Accept list-of-str only; normalize: strip + dedup + drop empty.
        seen = set()
        cleaned_list: list[str] = []
        for a in (aliases or []):
            if not isinstance(a, str):
                continue
            s = a.strip()
            if s and s.casefold() not in seen:
                seen.add(s.casefold())
                cleaned_list.append(s)
        co.aliases = cleaned_list
        changed.append("aliases")
    if notes is not _COMPANY_FIELD_UNSET:
        co.notes = (
            (str(notes).strip() or None) if notes is not None else None
        )
        changed.append("notes")
    await session.flush()
    if changed:
        logger.debug("Updated company %d fields=%s", company_id, changed)
    return True


async def delete_company(session: AsyncSession, company_id: int) -> bool:
    """Drop the company; vacancies survive with ``company_id = NULL``.

    Mirrors ``delete_hr``'s SET-NULL-on-vacancies stance: a vacancy is
    intrinsic to its source channel, not to the company tag we attached.
    Caller commits.
    """
    co = await session.get(Company, company_id)
    if co is None:
        return False
    co_name = co.name
    detached = (
        await session.execute(
            update(Vacancy)
            .where(Vacancy.company_id == company_id)
            .values(company_id=None)
        )
    ).rowcount
    await session.delete(co)
    logger.info(
        "Deleted company %d (%r), detached %d vacancies",
        company_id,
        co_name,
        int(detached or 0),
    )
    return True


async def merge_company(
    session: AsyncSession, *, absorbed_id: int, survivor_id: int
) -> None:
    """Merge ``absorbed`` company into ``survivor``. Irreversible.

    Caller must wrap in ``session.begin()``.
    """
    if absorbed_id == survivor_id:
        raise ValueError("merge_company: absorbed_id == survivor_id")
    absorbed = await session.get(Company, absorbed_id)
    survivor = await session.get(Company, survivor_id)
    if absorbed is None or survivor is None:
        raise ValueError(
            f"merge_company: not found "
            f"(absorbed={absorbed_id}, survivor={survivor_id})"
        )

    abs_name = absorbed.name
    abs_aliases = list(absorbed.aliases or [])
    abs_website = absorbed.website
    abs_notes = absorbed.notes

    moved_vacancies = (
        await session.execute(
            update(Vacancy)
            .where(Vacancy.company_id == absorbed_id)
            .values(company_id=survivor_id)
        )
    ).rowcount or 0

    await session.delete(absorbed)
    await session.flush()

    aliases = list(survivor.aliases or [])
    seen = {a.casefold() for a in aliases}
    for candidate in abs_aliases + [abs_name]:
        if candidate and candidate.casefold() not in seen:
            aliases.append(candidate)
            seen.add(candidate.casefold())
    survivor.aliases = aliases

    if not survivor.website and abs_website:
        survivor.website = abs_website
    survivor.notes = _concat_notes(survivor.notes, abs_notes)

    logger.info(
        "merged company #%d -> #%d (vacancies=%d)",
        absorbed_id, survivor_id, moved_vacancies,
    )
