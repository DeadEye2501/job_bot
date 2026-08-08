"""Поля одной вакансии."""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.models import Company, HR, Vacancy, VacancyEvent, VacancyStatusHistory
from backend.payloads import VacancyDetail

from backend.repository.vacancies_life import add_vacancy_event

logger = logging.getLogger(__name__)


async def get_vacancy_detail(
    session: AsyncSession, vacancy_id: int
) -> VacancyDetail | None:
    """Vacancy + status history + pipeline events, all sorted newest-first.

    Returns ``None`` if the vacancy doesn't exist. History and events are
    queried separately because there are no ORM relationships pointing
    Vacancy -> these tables (and adding them would silently double the
    write-side ON DELETE behaviour).
    """
    vacancy = (
        await session.scalars(
            select(Vacancy)
            .where(Vacancy.id == vacancy_id)
            .options(
                selectinload(Vacancy.hr),
                selectinload(Vacancy.company),
                selectinload(Vacancy.channel),
            )
        )
    ).first()
    if vacancy is None:
        return None

    history = list(
        (
            await session.scalars(
                select(VacancyStatusHistory)
                .where(VacancyStatusHistory.vacancy_id == vacancy_id)
                .order_by(
                    VacancyStatusHistory.changed_at.desc(),
                    VacancyStatusHistory.id.desc(),
                )
            )
        ).all()
    )
    events = list(
        (
            await session.scalars(
                select(VacancyEvent)
                .where(VacancyEvent.vacancy_id == vacancy_id)
                .order_by(
                    VacancyEvent.created_at.desc(),
                    VacancyEvent.id.desc(),
                )
            )
        ).all()
    )
    return VacancyDetail(vacancy=vacancy, history=history, events=events)


async def update_vacancy_notes(
    session: AsyncSession, vacancy_id: int, notes: str | None
) -> bool:
    """Replace ``vacancy.notes``. Returns False if the vacancy is missing.

    Empty / whitespace-only ``notes`` is normalized to ``NULL`` so a textarea
    with only spaces or newlines doesn't leave behind a "ghost" non-empty
    value that the UI can't tell apart from real notes. Leading / trailing
    whitespace inside otherwise non-empty notes is preserved verbatim so the
    JS-side baseline (``notesLastSaved``) matches the textarea content
    character-for-character on the next debounce — otherwise we'd be re-saving
    the same trimmed string on every keystroke.
    """
    vacancy = await session.get(Vacancy, vacancy_id)
    if vacancy is None:
        return False
    normalized: str | None
    if notes is None or not notes.strip():
        normalized = None
    else:
        normalized = notes
    vacancy.notes = normalized
    await session.flush()
    return True


async def set_vacancy_hr(
    session: AsyncSession, vacancy_id: int, hr_id: int | None
) -> bool:
    """Link or unlink the HR for a vacancy. Returns False if vacancy missing."""
    vacancy = await session.get(Vacancy, vacancy_id)
    if vacancy is None:
        return False
    previous_hr_id = vacancy.hr_id
    target_hr: HR | None = None
    if hr_id is not None:
        target_hr = await session.get(HR, hr_id)
        if target_hr is None:
            raise ValueError(f"set_vacancy_hr: HR {hr_id} does not exist")
    if previous_hr_id == hr_id:
        # No effective change -> no timeline noise.
        return True
    previous_name: str | None = None
    if previous_hr_id is not None:
        prev_hr = await session.get(HR, previous_hr_id)
        if prev_hr is not None:
            previous_name = prev_hr.name or prev_hr.telegram_username
    next_name: str | None = None
    if target_hr is not None:
        next_name = target_hr.name or target_hr.telegram_username
    vacancy.hr_id = hr_id
    await add_vacancy_event(
        session,
        vacancy_id,
        kind="linked_hr",
        payload={
            "previous_id": previous_hr_id,
            "previous_name": previous_name,
            "new_id": hr_id,
            "new_name": next_name,
        },
    )
    await session.flush()
    logger.info(
        "vacancy %d: hr_id %s -> %s",
        vacancy_id,
        previous_hr_id,
        hr_id,
    )
    return True


async def set_vacancy_company(
    session: AsyncSession, vacancy_id: int, company_id: int | None
) -> bool:
    """Link or unlink the company for a vacancy. False if vacancy missing."""
    vacancy = await session.get(Vacancy, vacancy_id)
    if vacancy is None:
        return False
    previous_company_id = vacancy.company_id
    target_company: Company | None = None
    if company_id is not None:
        target_company = await session.get(Company, company_id)
        if target_company is None:
            raise ValueError(
                f"set_vacancy_company: company {company_id} does not exist"
            )
    if previous_company_id == company_id:
        return True
    previous_name: str | None = None
    if previous_company_id is not None:
        prev_company = await session.get(Company, previous_company_id)
        if prev_company is not None:
            previous_name = prev_company.name
    next_name: str | None = None
    if target_company is not None:
        next_name = target_company.name
    vacancy.company_id = company_id
    await add_vacancy_event(
        session,
        vacancy_id,
        kind="linked_company",
        payload={
            "previous_id": previous_company_id,
            "previous_name": previous_name,
            "new_id": company_id,
            "new_name": next_name,
        },
    )
    await session.flush()
    logger.info(
        "vacancy %d: company_id %s -> %s",
        vacancy_id,
        previous_company_id,
        company_id,
    )
    return True
