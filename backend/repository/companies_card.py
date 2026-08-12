"""Ведение записей о компаниях."""

import logging
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.spellings import dedupe_first_wins
from backend.models import Company, Vacancy
from backend.payloads import CompanyDetail, str_list

from backend.repository.blacklist_marks import (
    active_blacklist_value,
    preferred_blacklist_value,
)
from backend.repository.merging import concat_notes, load_merge_pair
from backend.repository.vacancies_life import repoint_vacancies

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

    Единственное место, где заводится строка компании: и по кнопке из окна,
    и сведением разобранной вакансии. Сайт готовит зовущий — конвейер не
    пускает в колонку ссылки на агрегаторы, окно кладёт введённое как есть.

    Unique constraint on ``company.name`` will surface as IntegrityError if
    the user tries to create a duplicate. Окно превращает его в сообщение
    человеку, конвейер — в два исхода сведения, поэтому здесь он не
    перехватывается.
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

    Написание одно, и оно же попадает в кнопку «в чёрный список»
    (см. `preferred_blacklist_value`).
    """
    return [co.name] if co.name else []


def company_blacklist_preferred_value(co: Company) -> str | None:
    return preferred_blacklist_value(company_blacklist_candidates(co))


async def _company_blacklist_value(
    session: AsyncSession, co: Company
) -> str | None:
    return await active_blacklist_value(
        session, "company", company_blacklist_candidates(co)
    )


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


def _set_aliases(co: Company, aliases) -> None:
    """Записать написания компании, не сверяя их с её именем.

    Accept list-of-str only; normalize: strip + dedup + drop empty. А вот с
    именем компании набранное здесь не сверяется намеренно: список человек
    пишет руками, и выбросить написанное им значило бы стереть введённое
    молча. Слияние сверяется — там список копится сам.
    """
    co.aliases = dedupe_first_wins(str_list(aliases), str.casefold)


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
        _set_aliases(co, aliases)
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
    detached = await repoint_vacancies(
        session, Vacancy.company_id, absorbed_id=company_id, survivor_id=None
    )
    await session.delete(co)
    logger.info(
        "Deleted company %d (%r), detached %d vacancies",
        company_id,
        co_name,
        int(detached or 0),
    )
    return True


@dataclass(frozen=True, slots=True)
class _AbsorbedCompany:
    """Что уносится с поглощаемой компанией; читается до удаления строки."""

    name: str
    aliases: list
    website: str | None
    notes: str | None


def _carry_company_to_survivor(
    survivor: Company, taken: _AbsorbedCompany
) -> None:
    """Перенести на выжившую компанию то, что не пропадает с поглощённой.

    Имя поглощённой становится её написанием: по нему компанию продолжают
    искать словами. Сравнение буквальное, без нормализации имён: список
    написаний читает не только сопоставление (ему хватило бы нормализованных
    форм), но и поиск по подстроке, и карточка компании. Написание,
    отброшенное как «сопоставлению ничего не даёт», исчезло бы из базы вместе
    с поглощённой строкой.

    Сайт берётся, только если своего нет, а заметки склеиваются — иначе
    написанное человеком пропадало бы молча.
    """
    aliases = list(survivor.aliases or [])
    known = {(survivor.name or "").casefold()}
    known.update(a.casefold() for a in aliases)
    survivor.aliases = aliases + dedupe_first_wins(
        taken.aliases + [taken.name], str.casefold, known
    )
    if not survivor.website and taken.website:
        survivor.website = taken.website
    survivor.notes = concat_notes(survivor.notes, taken.notes)


async def merge_company(
    session: AsyncSession, *, absorbed_id: int, survivor_id: int
) -> None:
    """Merge ``absorbed`` company into ``survivor``. Irreversible.

    Caller must wrap in ``session.begin()``.
    """
    absorbed, survivor = await load_merge_pair(
        session,
        Company,
        absorbed_id=absorbed_id,
        survivor_id=survivor_id,
        subject="merge_company",
    )
    taken = _AbsorbedCompany(
        name=absorbed.name,
        aliases=list(absorbed.aliases or []),
        website=absorbed.website,
        notes=absorbed.notes,
    )
    moved_vacancies = await repoint_vacancies(
        session,
        Vacancy.company_id,
        absorbed_id=absorbed_id,
        survivor_id=survivor_id,
    )
    await session.delete(absorbed)
    await session.flush()
    _carry_company_to_survivor(survivor, taken)

    logger.info(
        "merged company #%d -> #%d (vacancies=%d)",
        absorbed_id, survivor_id, moved_vacancies,
    )
