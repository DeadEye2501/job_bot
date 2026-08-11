"""Поля одной вакансии."""

import logging

from dataclasses import dataclass
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.models import Company, HR, Vacancy, VacancyEvent, VacancyStatusHistory
from backend.payloads import VacancyDetail

from backend.repository.vacancies_life import add_vacancy_event

logger = logging.getLogger(__name__)

VACANCY_NEIGHBOURS = (
    selectinload(Vacancy.hr),
    selectinload(Vacancy.company),
    selectinload(Vacancy.channel),
)
"""Соседи вакансии, без которых её не показать: HR, компания, канал.

Подгружаются они и карточкой, и списком, и перечень у них один. Забытый здесь
сосед не превращается в пустое поле: связь читают уже за пределами сессии, и
незагруженная бросает — а бросок съедает диспетчер моста, отвечая окну пустым
списком. Это уже наблюдали, и след записан у `vacancies_mini`.
"""


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
            .options(*VACANCY_NEIGHBOURS)
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


@dataclass(frozen=True, slots=True)
class _Link:
    """Чем перепривязка вакансии к одному предмету отличается от другой.

    Сам распорядок у них общий: не изменилось — молчим, не существует —
    отказ, а состоявшаяся перепривязка попадает в ленту с именами до и
    после. Различаются колонка, таблица, род записи в ленте и то, как у
    предмета спросить имя.
    """

    column: str
    model: type
    kind: str
    display: Callable[[Any], str | None]
    # Имя действия, а не рода записи в ленте: текст отказа мост
    # показывает пользователю подсказкой как есть.
    operation: str


_HR_LINK = _Link(
    column="hr_id",
    model=HR,
    kind="linked_hr",
    display=lambda hr: hr.name or hr.telegram_username,
    operation="set_vacancy_hr",
)


_COMPANY_LINK = _Link(
    column="company_id",
    model=Company,
    kind="linked_company",
    display=lambda company: company.name,
    operation="set_vacancy_company",
)


async def _relink(
    session: AsyncSession, vacancy_id: int, new_id: int | None, link: _Link
) -> bool:
    """Перепривязать вакансию к предмету. False — вакансии нет вовсе.

    Совпадение с прежним значением возвращает успех, ничего не записав:
    иначе лента карточки полнилась бы строками «ничего не изменилось».
    """
    vacancy = await session.get(Vacancy, vacancy_id)
    if vacancy is None:
        return False
    previous_id = getattr(vacancy, link.column)
    target = None
    if new_id is not None:
        target = await session.get(link.model, new_id)
        if target is None:
            raise ValueError(
                f"{link.operation}: {link.model.__name__} {new_id} does not exist"
            )
    if previous_id == new_id:
        return True
    previous_name: str | None = None
    if previous_id is not None:
        previous = await session.get(link.model, previous_id)
        if previous is not None:
            previous_name = link.display(previous)
    setattr(vacancy, link.column, new_id)
    await add_vacancy_event(
        session,
        vacancy_id,
        kind=link.kind,
        payload={
            "previous_id": previous_id,
            "previous_name": previous_name,
            "new_id": new_id,
            "new_name": link.display(target) if target is not None else None,
        },
    )
    await session.flush()
    logger.info(
        "vacancy %d: %s %s -> %s", vacancy_id, link.column, previous_id, new_id
    )
    return True


async def set_vacancy_hr(
    session: AsyncSession, vacancy_id: int, hr_id: int | None
) -> bool:
    """Link or unlink the HR for a vacancy. Returns False if vacancy missing."""
    return await _relink(session, vacancy_id, hr_id, _HR_LINK)


async def set_vacancy_company(
    session: AsyncSession, vacancy_id: int, company_id: int | None
) -> bool:
    """Link or unlink the company for a vacancy. False if vacancy missing."""
    return await _relink(session, vacancy_id, company_id, _COMPANY_LINK)
