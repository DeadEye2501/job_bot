"""Отклик вне Telegram: строка, скрининг и Applied — одной транзакцией."""

from backend.models import (
    Application,
    ApplicationVia,
    Screening,
    Vacancy,
    VacancyEvent,
    VacancyStatus,
)
from backend.repository.applications import (
    ApplicationEntry,
    record_application,
    vacancy_screening,
)
from tests.dbio import all_rows, only_row, put
from tests.factories import at, vacancy_row
from tests.factories_aggregators import application_row, screening_row


def _entry(vacancy_id, **over) -> ApplicationEntry:
    fields = dict(vacancy_id=vacancy_id, aggregator_id=None, via=ApplicationVia.FORM,
                  target="https://site.test/form", letter="Письмо", letter_by="app",
                  screening=[(False, "Вопрос"), (True, "Ответ")], simulated=False)
    fields.update(over)
    return ApplicationEntry(**fields)


async def _record(session, entry, forced=False):
    async with session.begin():
        return await record_application(session, entry, forced=forced)


async def test_a_new_vacancy_gets_applied_with_its_screening(session, session_factory):
    vacancy = vacancy_row(status=VacancyStatus.NEW)
    await put(session_factory, vacancy)

    await _record(session, _entry(vacancy.id))

    assert (await only_row(session_factory, Vacancy)).status is VacancyStatus.APPLIED
    assert [(s.position, s.from_us, s.text) for s in await all_rows(session_factory, Screening)] == [
        (0, False, "Вопрос"), (1, True, "Ответ")
    ]


async def test_a_vacancy_moved_by_a_person_keeps_its_status(session, session_factory):
    """Автоматика ставит Applied только из New; отклик записывается, статус остаётся."""
    vacancy = vacancy_row(status=VacancyStatus.NOT_FIT)
    await put(session_factory, vacancy)

    await _record(session, _entry(vacancy.id))

    assert (await only_row(session_factory, Vacancy)).status is VacancyStatus.NOT_FIT
    assert len(await all_rows(session_factory, Application)) == 1


async def test_a_manual_application_moves_a_not_fit_vacancy(session, session_factory):
    vacancy = vacancy_row(status=VacancyStatus.NOT_FIT)
    await put(session_factory, vacancy)

    await _record(session, _entry(vacancy.id), forced=True)

    assert (await only_row(session_factory, Vacancy)).status is VacancyStatus.APPLIED


async def test_the_same_address_twice_adds_screening_not_a_row(session, session_factory):
    vacancy = vacancy_row()
    await put(session_factory, vacancy)
    first = await _record(session, _entry(vacancy.id))

    again = await _record(session, _entry(vacancy.id, screening=[(False, "Ещё вопрос")]))

    assert again == first
    assert len(await all_rows(session_factory, Application)) == 1
    assert [s.position for s in await all_rows(session_factory, Screening)] == [0, 1, 2]


async def test_the_feed_says_how_and_who_wrote_the_letter(session, session_factory):
    vacancy = vacancy_row()
    await put(session_factory, vacancy)

    await _record(session, _entry(vacancy.id, simulated=True, letter_by="agent"))

    (event,) = [e for e in await all_rows(session_factory, VacancyEvent)
                if e.kind == "applied_elsewhere"]
    assert event.payload == {"via": "form", "target": "https://site.test/form",
                             "simulated": True, "letter_by": "agent"}


async def test_the_same_address_typed_differently_is_the_same_application(session, session_factory):
    vacancy = vacancy_row()
    await put(session_factory, vacancy)
    first = await _record(session, _entry(vacancy.id, via=ApplicationVia.EMAIL, target="HR@Site.test"))

    again = await _record(session, _entry(vacancy.id, via=ApplicationVia.EMAIL, target="hr@site.test"))

    assert again == first
    assert len(await all_rows(session_factory, Application)) == 1


async def test_the_screening_of_a_vacancy_goes_application_by_application(session, session_factory):
    """Отклик за откликом в порядке отправки, реплики по порядку; отклик без
    скрининга и чужая вакансия в выборку не попадают."""
    vacancy, other = vacancy_row(), vacancy_row()
    await put(session_factory, vacancy, other)
    late = application_row(vacancy.id, target="https://late.test/", sent_at=at(10))
    early = application_row(vacancy.id, target="hr@early.test", sent_at=at(0))
    silent = application_row(vacancy.id, target="https://silent.test/", sent_at=at(5))
    foreign = application_row(other.id, sent_at=at(0))
    await put(session_factory, late, early, silent, foreign)
    await put(session_factory,
              screening_row(late.id, 1, from_us=True, text="Пять"),
              screening_row(late.id, 0, text="Сколько лет опыта?"),
              screening_row(early.id, 0, text="Когда можете выйти?"),
              screening_row(foreign.id, 0, text="Чужой вопрос"))

    shown = await vacancy_screening(session, vacancy.id)

    assert [(one.target, one.lines) for one in shown] == [
        ("hr@early.test", [(False, "Когда можете выйти?")]),
        ("https://late.test/", [(False, "Сколько лет опыта?"), (True, "Пять")]),
    ]
