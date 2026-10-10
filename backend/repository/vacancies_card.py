"""Поля одной вакансии."""

import logging

from dataclasses import dataclass
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.models import Company, HR, Vacancy, VacancyEvent, VacancyStatusHistory
from backend.payloads import VacancyDetail

from backend.repository.applications import has_screening
from backend.repository.vacancies_life import add_vacancy_event
from backend.repository.vacancy_contacts import list_contacts

logger = logging.getLogger(__name__)

VACANCY_NEIGHBOURS = (
    selectinload(Vacancy.hr),
    selectinload(Vacancy.company),
    selectinload(Vacancy.channel),
    selectinload(Vacancy.aggregator),
)
"""Соседи вакансии, без которых её не показать: HR, компания, источник — канал
или агрегатор.

Подгружаются они и карточкой, и списком, и перечень у них один. Забытый здесь
сосед не превращается в пустое поле: связь читают уже за пределами сессии, и
незагруженная бросает — а бросок съедает диспетчер моста, отвечая окну пустым
списком. Это уже наблюдали, и след записан у `vacancies_mini`.
"""


async def _newest_first(
    session: AsyncSession, model, stamp, vacancy_id: int
) -> list:
    """Записи одной ленты вакансии, свежие сверху.

    Лент у карточки две — переходы статусов и события конвейера, — и разное у
    них только имя колонки со временем.

    Разрешитель по идентификатору не украшение: время проставляет база, и две
    записи подряд легко получают одну метку.
    """
    return list(
        (
            await session.scalars(
                select(model)
                .where(model.vacancy_id == vacancy_id)
                .order_by(stamp.desc(), model.id.desc())
            )
        ).all()
    )


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

    return VacancyDetail(
        vacancy=vacancy,
        history=await _newest_first(
            session, VacancyStatusHistory, VacancyStatusHistory.changed_at, vacancy_id
        ),
        events=await _newest_first(
            session, VacancyEvent, VacancyEvent.created_at, vacancy_id
        ),
        contacts=await list_contacts(session, vacancy_id),
        has_screening=await has_screening(session, vacancy_id),
    )


async def update_vacancy_notes(
    session: AsyncSession, vacancy_id: int, notes: str | None
) -> Vacancy | None:
    """Replace ``vacancy.notes``. Пусто — такой вакансии нет.

    Empty / whitespace-only ``notes`` is normalized to ``NULL`` so a textarea
    with only spaces or newlines doesn't leave behind a "ghost" non-empty
    value that the UI can't tell apart from real notes. Leading / trailing
    whitespace inside otherwise non-empty notes is preserved verbatim so the
    JS-side baseline (``notesLastSaved``) matches the textarea content
    character-for-character on the next debounce — otherwise we'd be re-saving
    the same trimmed string on every keystroke.

    Отдаётся сама строка, а не признак «записали»: окно принимает ответ за
    исходное состояние поля, и знать ему надо не «получилось ли», а что
    именно легло после сведения пустого к `NULL`. Строка эта уже в руках —
    зовущему пришлось бы читать её вторым запросом. `None` значит «такой
    вакансии нет».
    """
    vacancy = await session.get(Vacancy, vacancy_id)
    if vacancy is None:
        return None
    normalized: str | None
    if notes is None or not notes.strip():
        normalized = None
    else:
        normalized = notes
    vacancy.notes = normalized
    await session.flush()
    return vacancy


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


async def _link_name(
    session: AsyncSession, link: _Link, row_id: int | None
) -> str | None:
    """Как назвать привязанный предмет в ленте; пусто — назвать нечем.

    Имя записывается в саму строку ленты, а не берётся по ссылке при показе:
    предмет могут переименовать или снести, и тогда прошлая запись ленты
    осталась бы без объяснения, что именно поменяли.
    """
    if row_id is None:
        return None
    row = await session.get(link.model, row_id)
    return link.display(row) if row is not None else None


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
    # До присвоения: чтение по промаху карты объектов сбрасывает висящие правки.
    previous_name = await _link_name(session, link, previous_id)
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
