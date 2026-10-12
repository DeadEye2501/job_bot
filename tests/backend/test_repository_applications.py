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


async def _record(session, entry):
    async with session.begin():
        return await record_application(session, entry)


async def test_a_new_vacancy_gets_applied_with_its_screening(session, session_factory):
    vacancy = vacancy_row(status=VacancyStatus.NEW)
    await put(session_factory, vacancy)

    await _record(session, _entry(vacancy.id))

    assert (await only_row(session_factory, Vacancy)).status is VacancyStatus.APPLIED
    assert [(s.position, s.from_us, s.text) for s in await all_rows(session_factory, Screening)] == [
        (0, False, "Вопрос"), (1, True, "Ответ")
    ]


async def test_an_application_leaves_one_applied_event(session_factory):
    row = vacancy_row(status=VacancyStatus.DECLINE)
    await put(session_factory, row)
    async with session_factory() as session:
        async with session.begin():
            await record_application(session, ApplicationEntry(
                vacancy_id=row.id, aggregator_id=None, via=ApplicationVia.EMAIL,
                target="hr@company.test", letter="Письмо", letter_by="app",
                screening=[], simulated=False))
    (event,) = [e for e in await all_rows(session_factory, VacancyEvent)]
    assert event.kind == "applied" and event.payload["via"] == "email"
    assert (await only_row(session_factory, Vacancy)).status is VacancyStatus.APPLIED


async def test_a_new_application_to_the_same_address_is_its_own(session, session_factory):
    """Ручной отклик на отказ и прогон заново уходят тому же HR: каждый — свой
    отклик, и каждый снова ведёт вакансию в Applied."""
    vacancy = vacancy_row()
    await put(session_factory, vacancy)
    first = await _record(session, _entry(vacancy.id))
    async with session.begin():
        (await session.get(Vacancy, vacancy.id)).status = VacancyStatus.DECLINE

    again = await _record(session, _entry(vacancy.id))

    assert again != first and len(await all_rows(session_factory, Application)) == 2
    assert (await only_row(session_factory, Vacancy)).status is VacancyStatus.APPLIED
    assert [e.kind for e in await all_rows(session_factory, VacancyEvent)] == ["applied", "applied"]


async def test_the_feed_says_how_and_who_wrote_the_letter(session, session_factory):
    vacancy = vacancy_row()
    await put(session_factory, vacancy)

    await _record(session, _entry(vacancy.id, simulated=True, letter_by="agent"))

    (event,) = [e for e in await all_rows(session_factory, VacancyEvent)
                if e.kind == "applied"]
    assert event.payload == {"via": "form", "target": "https://site.test/form",
                             "simulated": True, "letter_by": "agent"}


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


async def test_the_letter_opens_its_application_as_our_first_line(session, session_factory):
    """Письмо — первое, что работодатель получил от нас: оно идёт первой репликой,
    и отклик, где было одно письмо без вопросов, в окне тоже есть."""
    vacancy = vacancy_row()
    await put(session_factory, vacancy)
    asked = application_row(vacancy.id, target="https://asked.test/", letter="Письмо А", sent_at=at(0))
    plain = application_row(vacancy.id, target="hr@plain.test", letter="Письмо Б", sent_at=at(5))
    await put(session_factory, asked, plain)
    await put(session_factory, screening_row(asked.id, 0, text="Сколько лет опыта?"))

    shown = await vacancy_screening(session, vacancy.id)

    assert [(one.target, one.lines) for one in shown] == [
        ("https://asked.test/", [(True, "Письмо А"), (False, "Сколько лет опыта?")]),
        ("hr@plain.test", [(True, "Письмо Б")]),
    ]
