"""Контакт, найденный разбором, ложится контактом вакансии, а заметки остаются
человеку.

Иногда в объявлении вместо Telegram дана почта или форма; без этого
пользователь остался бы с вакансией, на которую нечем ответить. Разбор
заменяет только свою находку: добавленное агентом и человеком он не трогает.
"""

from backend.flows import parse
from backend.models import ContactAddedBy, Vacancy, VacancyContact
from backend.repository.vacancies_card import update_vacancy_notes
from backend.repository.vacancy_contacts import add_contact
from tests.dbio import all_rows, only_row, put
from tests.factories import parsed_vacancy
from tests.factories_aggregators import vacancy_contact_row


async def _contacts(session_factory) -> list[tuple[str, str, str]]:
    rows = await all_rows(session_factory, VacancyContact)
    return sorted((c.value, c.match_key, c.added_by.value) for c in rows)


async def test_an_extra_way_to_apply_becomes_a_contact_of_the_vacancy(
    parsing, session_factory
):
    """Не-телеграмный способ отклика ложится контактом вакансии, а не в заметки."""
    pipeline, vacancy = parsing
    pipeline.parsed = parsed_vacancy(
        title="Python-разработчик", stack_required=["Python"],
        other_contact="Jobs@Example.com",
    )

    await parse.parse_and_update_vacancy(
        pipeline, vacancy.id, "текст", "jobs", allow_delete=False
    )

    assert await _contacts(session_factory) == [
        ("Jobs@Example.com", "jobs@example.com", "parse")
    ]
    assert (await only_row(session_factory, Vacancy)).notes is None


async def test_the_parse_leaves_the_persons_notes_alone(parsing, session_factory):
    """Заметка человека переживает разбор с найденным контактом."""
    pipeline, vacancy = parsing
    async with session_factory() as session:
        async with session.begin():
            await update_vacancy_notes(session, vacancy.id, "звонить после обеда")
    pipeline.parsed = parsed_vacancy(
        title="Python-разработчик", other_contact="jobs@example.com"
    )

    await parse.parse_and_update_vacancy(
        pipeline, vacancy.id, "текст", "jobs", allow_delete=False
    )

    assert (await only_row(session_factory, Vacancy)).notes == "звонить после обеда"


async def test_a_parse_without_a_contact_drops_only_what_the_parse_found(
    parsing, session_factory
):
    """Разбор без контакта убирает свои строки. Добавленное агентом и человеком
    остаётся."""
    pipeline, vacancy = parsing
    await put(
        session_factory,
        vacancy_contact_row(vacancy.id, "old@x.ru", added_by=ContactAddedBy.PARSE),
        vacancy_contact_row(vacancy.id, "agent@x.ru", added_by=ContactAddedBy.AGENT),
        vacancy_contact_row(vacancy.id, "mine@x.ru", added_by=ContactAddedBy.USER),
    )
    pipeline.parsed = parsed_vacancy(title="Python-разработчик", other_contact=None)

    await parse.parse_and_update_vacancy(
        pipeline, vacancy.id, "текст", "jobs", allow_delete=False
    )

    assert [v for v, _, _ in await _contacts(session_factory)] == [
        "agent@x.ru", "mine@x.ru"
    ]


async def test_an_empty_parse_leaves_the_notes_alone(parsing, session_factory):
    """Разбор, не давший ничего, стирает свои поля, но не заметку человека."""
    pipeline, vacancy = parsing
    async with session_factory() as session:
        async with session.begin():
            await update_vacancy_notes(session, vacancy.id, "звонить после обеда")
    pipeline.parsed = None

    await parse.parse_and_update_vacancy(
        pipeline, vacancy.id, "текст", "jobs", allow_delete=False
    )

    assert (await only_row(session_factory, Vacancy)).notes == "звонить после обеда"


async def test_a_contact_found_again_keeps_its_row(parsing, session_factory):
    """Повторная находка того же контакта не пересоздаёт строку: номер прежний."""
    pipeline, vacancy = parsing
    found = vacancy_contact_row(
        vacancy.id, "jobs@example.com", added_by=ContactAddedBy.PARSE
    )
    await put(session_factory, found)
    pipeline.parsed = parsed_vacancy(
        title="Python-разработчик", other_contact="jobs@example.com"
    )

    await parse.parse_and_update_vacancy(
        pipeline, vacancy.id, "текст", "jobs", allow_delete=False
    )

    assert [c.id for c in await all_rows(session_factory, VacancyContact)] == [found.id]


async def test_a_contact_the_person_confirmed_survives_the_next_parse(
    parsing, session_factory
):
    """Человек добавил то, что разбор уже нашёл: строка становится его, и
    разбор без контакта её больше не убирает."""
    pipeline, vacancy = parsing
    await put(
        session_factory,
        vacancy_contact_row(vacancy.id, "jobs@example.com", added_by=ContactAddedBy.PARSE),
    )
    async with session_factory() as session:
        async with session.begin():
            await add_contact(session, vacancy.id, "JOBS@example.com", ContactAddedBy.USER)
    pipeline.parsed = parsed_vacancy(title="Python-разработчик", other_contact=None)

    await parse.parse_and_update_vacancy(
        pipeline, vacancy.id, "текст", "jobs", allow_delete=False
    )

    assert await _contacts(session_factory) == [
        ("jobs@example.com", "jobs@example.com", "user")
    ]


async def test_a_contact_already_known_is_not_doubled(parsing, session_factory):
    """Разбор нашёл контакт, который человек уже добавил: строка одна, и она
    человеческая. Прежняя находка разбора с другим ключом уходит."""
    pipeline, vacancy = parsing
    await put(
        session_factory,
        vacancy_contact_row(vacancy.id, "jobs@example.com", added_by=ContactAddedBy.USER),
        vacancy_contact_row(vacancy.id, "old@x.ru", added_by=ContactAddedBy.PARSE),
    )
    pipeline.parsed = parsed_vacancy(
        title="Python-разработчик", other_contact="JOBS@example.com"
    )

    await parse.parse_and_update_vacancy(
        pipeline, vacancy.id, "текст", "jobs", allow_delete=False
    )

    assert await _contacts(session_factory) == [
        ("jobs@example.com", "jobs@example.com", "user")
    ]


async def test_contacts_listed_with_commas_become_separate_rows(
    parsing, session_factory
):
    """Строка с несколькими контактами через запятую ложится строкой на каждый:
    одной записью её не узнать ни по почте, ни по ссылке. Запятая внутри
    ссылки перечнем не считается."""
    pipeline, vacancy = parsing
    pipeline.parsed = parsed_vacancy(
        title="Python-разработчик",
        other_contact="jobs@example.com, https://example.com/a,b-c,  +7 999 123-45-67",
    )

    await parse.parse_and_update_vacancy(
        pipeline, vacancy.id, "текст", "jobs", allow_delete=False
    )

    assert await _contacts(session_factory) == [
        ("+7 999 123-45-67", "79991234567", "parse"),
        ("https://example.com/a,b-c", "example.com/a,b-c", "parse"),
        ("jobs@example.com", "jobs@example.com", "parse"),
    ]


async def test_a_comma_inside_a_phrase_does_not_make_a_contact_without_address(
    parsing, session_factory
):
    """Часть перечня без адреса — продолжение соседнего контакта, а не контакт:
    по ней откликнуться некуда."""
    pipeline, vacancy = parsing
    pipeline.parsed = parsed_vacancy(
        title="Python-разработчик",
        other_contact="Для резюме, почта jobs@example.com, в теме укажите вакансию, "
        "+7 999 123-45-67, доб. 12",
    )

    await parse.parse_and_update_vacancy(
        pipeline, vacancy.id, "текст", "jobs", allow_delete=False
    )

    assert sorted(v for v, _, _ in await _contacts(session_factory)) == [
        "+7 999 123-45-67, доб. 12",
        "Для резюме, почта jobs@example.com, в теме укажите вакансию",
    ]


async def test_a_reparse_keeps_every_contact_it_found_again(parsing, session_factory):
    """Повторный разбор оставляет все свои находки из перечня в прежнем
    написании, а не только одну, и убирает ту, которой в перечне больше нет."""
    pipeline, vacancy = parsing
    await put(
        session_factory,
        *(
            vacancy_contact_row(
                vacancy.id, value, match_key=value.lower(), added_by=ContactAddedBy.PARSE
            )
            for value in ("JOBS@example.com", "HR@example.com", "old@example.com")
        ),
    )
    pipeline.parsed = parsed_vacancy(
        title="Python-разработчик", other_contact="jobs@example.com, hr@example.com"
    )

    await parse.parse_and_update_vacancy(
        pipeline, vacancy.id, "текст", "jobs", allow_delete=False
    )

    assert [v for v, _, _ in await _contacts(session_factory)] == [
        "HR@example.com", "JOBS@example.com"
    ]
