"""Контакты вакансии в карточке: человек добавляет и удаляет их руками."""

import pytest

from backend.models import ContactAddedBy
from tests.dbio import put
from tests.factories import vacancy_row
from tests.factories_aggregators import vacancy_contact_row


async def test_an_added_contact_shows_up_on_the_card(api, ask, session_factory):
    """Добавленный контакт виден в карточке как добавленный человеком."""
    vacancy = vacancy_row()
    await put(session_factory, vacancy)

    await ask(api.vacancies.add_contact, {"vacancy_id": vacancy.id, "value": " hr@x.ru "})

    card = await ask(api.vacancies.detail, vacancy.id)
    assert [(c["value"], c["added_by"]) for c in card["ok"]["vacancy"]["contacts"]] == [
        ("hr@x.ru", "user")
    ]


async def test_a_contact_written_another_way_is_not_added_twice(
    api, ask, session_factory
):
    """Тот же контакт в другом написании второй строкой не ложится."""
    vacancy = vacancy_row()
    await put(session_factory, vacancy)
    await put(
        session_factory,
        vacancy_contact_row(vacancy.id, "hr@x.ru", added_by=ContactAddedBy.PARSE),
    )

    answer = await ask(
        api.vacancies.add_contact, {"vacancy_id": vacancy.id, "value": "HR@X.ru"}
    )

    assert [c["value"] for c in answer["ok"]["contacts"]] == ["hr@x.ru"]


@pytest.mark.parametrize("value", ["  ", "mailto:"])
async def test_an_empty_contact_is_refused(api, ask, session_factory, value):
    """Пусто и то, от чего после приведения ничего не осталось, — отказ, а не
    молчаливое «готово» без строки."""
    vacancy = vacancy_row()
    await put(session_factory, vacancy)

    answer = await ask(api.vacancies.add_contact, {"vacancy_id": vacancy.id, "value": value})

    assert answer["fail"] == "denied"


async def test_a_contact_for_a_missing_vacancy_is_refused(api, ask):
    answer = await ask(api.vacancies.add_contact, {"vacancy_id": 999, "value": "a@x.ru"})

    assert answer["fail"] == "denied"


async def test_a_deleted_contact_leaves_the_card(api, ask, session_factory):
    """Удалить можно любой контакт, и найденный разбором тоже."""
    vacancy = vacancy_row()
    await put(session_factory, vacancy)
    found = vacancy_contact_row(vacancy.id, "a@x.ru", added_by=ContactAddedBy.PARSE)
    await put(session_factory, found, vacancy_contact_row(vacancy.id, "b@x.ru"))

    answer = await ask(api.vacancies.delete_contact, {"contact_id": found.id})

    assert answer["ok"]["vacancy_id"] == vacancy.id
    card = await ask(api.vacancies.detail, vacancy.id)
    assert [c["value"] for c in card["ok"]["vacancy"]["contacts"]] == ["b@x.ru"]


async def test_deleting_a_missing_contact_is_refused(api, ask):
    answer = await ask(api.vacancies.delete_contact, {"contact_id": 999})

    assert answer["fail"] == "denied"
