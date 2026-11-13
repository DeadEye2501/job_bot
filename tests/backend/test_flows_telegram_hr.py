"""Telegram вакансии после разбора: человек — HR, и он один; прочий Telegram — контакты.

Записи Telegram — названный разбором HR, прочие контакты разбора и записанное
искателем — делятся вопросом к Telegram на людей и прочих. Не ответил Telegram
и на повтор — всё остаётся, как нашёл разбор.
"""

from types import SimpleNamespace

from pyrogram.errors import FloodWait

from backend.domain.contact_keys import contact_key
from backend.flows import parse
from backend.models import HR, ContactAddedBy, Vacancy, VacancyContact
from tests.dbio import all_rows, only_row, put
from tests.factories import parsed_vacancy
from tests.factories_aggregators import vacancy_contact_row
from tests.fakes.telegram import FakeTelegramClient
from tests.fakes.telegram_objects import user

_PEOPLE = {
    "anna_hr": user(id=1, username="anna_hr", first_name="Анна"),
    "boris_hr": user(id=2, username="boris_hr", first_name="Борис"),
}
_CHANNELS = {"jobs_channel": SimpleNamespace(id=-100)}


async def _parse(parsing, hr_contact=None, others=(), client=None):
    pipeline, vacancy = parsing
    pipeline.client = client or FakeTelegramClient(users=_PEOPLE, chats=_CHANNELS)
    pipeline.parsed = parsed_vacancy(
        title="Python-разработчик", stack_required=["Python"], hr_contact=hr_contact, other_contacts=list(others),
    )
    await parse.parse_and_update_vacancy(pipeline, vacancy.id, "текст", "jobs", allow_delete=False)


async def _hr_name(session_factory) -> str | None:
    vacancy = await only_row(session_factory, Vacancy)
    hrs = {hr.id: hr.telegram_username for hr in await all_rows(session_factory, HR)}
    return hrs.get(vacancy.hr_id)


async def _contacts(session_factory) -> list[str]:
    return sorted(row.value for row in await all_rows(session_factory, VacancyContact))


async def test_a_named_channel_goes_to_contacts_and_the_person_becomes_the_hr(parsing, session_factory):
    await _parse(parsing, hr_contact="@jobs_channel", others=["@anna_hr", "hr@acme.com"])

    assert await _hr_name(session_factory) == "anna_hr"
    assert (await only_row(session_factory, Vacancy)).hr_contact == "@anna_hr"
    assert await _contacts(session_factory) == ["@jobs_channel", "hr@acme.com"]


async def test_the_named_person_wins_and_other_people_are_dropped(parsing, session_factory):
    """HR у вакансии один: прочие люди не ложатся ни в HR, ни в контакты."""
    await _parse(parsing, hr_contact="@boris_hr", others=["@anna_hr"])

    assert await _hr_name(session_factory) == "boris_hr"
    assert await _contacts(session_factory) == []


async def test_without_a_named_person_the_first_person_becomes_the_hr(parsing, session_factory):
    await _parse(parsing, others=["https://t.me/jobs_channel/15", "t.me/boris_hr", "@anna_hr"])

    assert await _hr_name(session_factory) == "boris_hr"
    assert await _contacts(session_factory) == ["https://t.me/jobs_channel/15"]


async def test_a_person_the_seeker_wrote_down_becomes_the_hr_and_leaves_the_contacts(parsing, session_factory):
    """Записанное искателем со страницы проходит тот же шаг: человек уходит из контактов в HR."""
    _, vacancy = parsing
    await put(
        session_factory,
        *(vacancy_contact_row(vacancy.id, value, match_key=contact_key(value), added_by=ContactAddedBy.AGENT)
          for value in ("https://t.me/anna_hr", "https://t.me/jobs_channel/15")),
    )

    await _parse(parsing)

    assert await _hr_name(session_factory) == "anna_hr"
    assert await _contacts(session_factory) == ["https://t.me/jobs_channel/15"]


async def test_a_person_the_seeker_wrote_down_is_dropped_when_the_parse_named_another(parsing, session_factory):
    _, vacancy = parsing
    await put(session_factory, vacancy_contact_row(
        vacancy.id, "https://t.me/anna_hr", match_key=contact_key("https://t.me/anna_hr"),
        added_by=ContactAddedBy.AGENT))

    await _parse(parsing, hr_contact="@boris_hr")

    assert await _hr_name(session_factory) == "boris_hr"
    assert await _contacts(session_factory) == []


async def test_a_telegram_written_by_the_person_stays_untouched(parsing, session_factory):
    """Вписанное человеком — его решение: шаг его не спрашивает и не убирает."""
    _, vacancy = parsing
    await put(session_factory, vacancy_contact_row(
        vacancy.id, "https://t.me/anna_hr", match_key=contact_key("https://t.me/anna_hr"),
        added_by=ContactAddedBy.USER))

    await _parse(parsing)

    assert await _hr_name(session_factory) is None
    assert await _contacts(session_factory) == ["https://t.me/anna_hr"]


async def test_a_bare_named_channel_goes_to_contacts_as_telegram(parsing, session_factory):
    """Разбор назвал HR голым ником, а это канал: в контакты он ложится с `@`, а не простым словом."""
    await _parse(parsing, hr_contact="jobs_channel")

    assert await _contacts(session_factory) == ["@jobs_channel"]


async def test_a_nick_written_in_another_case_is_the_same_person(parsing, session_factory):
    await _parse(parsing, hr_contact="@Anna_HR")

    assert await _hr_name(session_factory) == "anna_hr"


async def test_one_failed_question_is_asked_again(parsing, session_factory):
    client = FakeTelegramClient(users=_PEOPLE, fails={"resolve_peer": [FloodWait(value=1), None]})

    await _parse(parsing, others=["@anna_hr"], client=client)

    assert await _hr_name(session_factory) == "anna_hr"


async def test_without_an_answer_twice_the_parse_is_kept_as_it_found_it(parsing, session_factory):
    """Кто за ником, неизвестно: шаг не делается, и Telegram ложится, как его нашёл разбор."""
    client = FakeTelegramClient(users=_PEOPLE, fails={"resolve_peer": FloodWait(value=1)})

    await _parse(parsing, hr_contact="@boris_hr", others=["@anna_hr"], client=client)

    assert await _hr_name(session_factory) is None
    assert (await only_row(session_factory, Vacancy)).hr_contact == "@boris_hr"
    assert await _contacts(session_factory) == ["@anna_hr"]
