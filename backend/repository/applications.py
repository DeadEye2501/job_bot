"""Отклики и скрининг по ним."""

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Application, ApplicationVia, Screening
from backend.repository.vacancies_life import add_vacancy_event
from backend.repository.vacancy_status import mark_vacancy_applied
from backend.telegram_time import utc_now

_EXPLANATION = {
    ApplicationVia.TELEGRAM: "Отклик в Telegram.",
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


async def record_application(session: AsyncSession, entry: ApplicationEntry) -> int:
    """Записать состоявшийся отклик: каждый — своя строка, статус и событие.

    Отклик на тот же адрес — прогон заново или ручной отклик на отказ — такой же
    отклик, как первый. Вопросы со страницы подтверждения в той же сессии агента
    дописываются к уже записанному (`append_screening`), а не сюда.

    Вызывающий держит транзакцию. Статус двигает `mark_vacancy_applied`.
    """
    row = Application(
        vacancy_id=entry.vacancy_id, aggregator_id=entry.aggregator_id, via=entry.via,
        target=entry.target, letter=entry.letter, sent_at=utc_now(),
    )
    session.add(row)
    await session.flush()
    await append_screening(session, row.id, entry.screening)
    await mark_vacancy_applied(session, entry.vacancy_id, _EXPLANATION[entry.via])
    await add_vacancy_event(session, entry.vacancy_id, "applied", {
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


@dataclass(frozen=True)
class ScreenedApplication:
    """Отклик в окне скрининга: куда ушёл и реплики «наша ли, текст» по порядку — письмо, затем вопросы и ответы."""

    target: str
    lines: list[tuple[bool, str]]


async def vacancy_screening(session: AsyncSession, vacancy_id: int) -> list[ScreenedApplication]:
    """Скрининг вакансии отклик за откликом, в порядке отправки; отклики без реплик пропущены.

    Письмо отклика — первая наша реплика: это первое, что работодатель от нас получил.
    """
    applications = (await session.execute(
        select(Application.id, Application.target, Application.letter)
        .where(Application.vacancy_id == vacancy_id)
        .order_by(Application.sent_at, Application.id)
    )).all()
    asked = await _screening_lines(session, [one.id for one in applications])
    shown = [
        ScreenedApplication(target, ([(True, letter)] if letter else []) + asked.get(application_id, []))
        for application_id, target, letter in applications
    ]
    return [one for one in shown if one.lines]


async def _screening_lines(
    session: AsyncSession, application_ids: list[int]
) -> dict[int, list[tuple[bool, str]]]:
    """Реплики скрининга этих откликов по порядку, сгруппированные по отклику."""
    rows = await session.execute(
        select(Screening.application_id, Screening.from_us, Screening.text)
        .where(Screening.application_id.in_(application_ids))
        .order_by(Screening.position)
    )
    lines: dict[int, list[tuple[bool, str]]] = {}
    for application_id, from_us, text in rows:
        lines.setdefault(application_id, []).append((from_us, text))
    return lines


async def has_screening(session: AsyncSession, vacancy_id: int) -> bool:
    """Есть ли что показать в окне скрининга. Из той же выборки, что и само окно:
    отдельное правило «что считать скринингом» разошлось бы с ним молча."""
    return bool(await vacancy_screening(session, vacancy_id))
