"""Отклики вне Telegram и скрининг по ним."""

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.contact_keys import contact_key
from backend.models import Application, ApplicationVia, Screening
from backend.repository.vacancies_life import add_vacancy_event
from backend.repository.vacancy_status import mark_vacancy_applied
from backend.telegram_time import utc_now

_EXPLANATION = {
    ApplicationVia.AGGREGATOR: "Отклик на сайте агрегатора.",
    ApplicationVia.FORM: "Отклик формой работодателя.",
    ApplicationVia.EMAIL: "Отклик письмом.",
}


@dataclass(frozen=True)
class ApplicationEntry:
    """Состоявшийся отклик. `letter_by` — значение из `LETTER_WRITERS`, если письмо было;
    `screening` — пары «наша ли реплика, текст» по порядку."""

    vacancy_id: int
    aggregator_id: int | None
    via: ApplicationVia
    target: str
    letter: str | None
    letter_by: str | None
    screening: list[tuple[bool, str]]
    simulated: bool


async def application_exists(session: AsyncSession, vacancy_id: int, target: str) -> bool:
    return await _existing(session, vacancy_id, target) is not None


async def record_application(session: AsyncSession, entry: ApplicationEntry, *, forced: bool) -> int:
    """Записать состоявшийся отклик. Тот же адрес второй строки не даёт — скрининг дописывается.

    Вызывающий держит транзакцию. Статус двигает граф: без `forced` — только из New.
    """
    known = await _existing(session, entry.vacancy_id, entry.target)
    if known is not None:
        await append_screening(session, known.id, entry.screening)
        return known.id
    row = Application(
        vacancy_id=entry.vacancy_id, aggregator_id=entry.aggregator_id, via=entry.via,
        target=entry.target, letter=entry.letter, sent_at=utc_now(),
    )
    session.add(row)
    await session.flush()
    await append_screening(session, row.id, entry.screening)
    await mark_vacancy_applied(session, entry.vacancy_id, _EXPLANATION[entry.via], force=forced)
    await add_vacancy_event(session, entry.vacancy_id, "applied_elsewhere", {
        "via": entry.via.value, "target": entry.target,
        "simulated": entry.simulated, "letter_by": entry.letter_by,
    })
    return row.id


async def append_screening(session: AsyncSession, application_id: int, lines) -> None:
    """Дописать реплики скрининга следом за уже записанными."""
    start = await session.scalar(
        select(func.count(Screening.id)).where(Screening.application_id == application_id)
    ) or 0
    for offset, (from_us, text) in enumerate(lines):
        session.add(Screening(application_id=application_id, from_us=from_us,
                              text=text, position=start + offset))


async def _existing(session: AsyncSession, vacancy_id: int, target: str) -> Application | None:
    """Отклик на тот же адрес — по ключу контакта, а не по написанию: `HR@Site.ru`
    и `hr@site.ru`, адрес с косой в конце и без — один адрес."""
    key = contact_key(target)
    rows = await session.scalars(select(Application).where(Application.vacancy_id == vacancy_id))
    return next((row for row in rows if contact_key(row.target) == key), None)
