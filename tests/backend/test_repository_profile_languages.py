"""Следствия замены списка языков профиля.

Языки заменяются целиком: их единицы, и полная замена держит запрет «один
язык дважды» сама собой — сверять список построчно незачем.
"""

import pytest

from backend.models import ProfileLanguage
from backend.repository.profile_languages import (
    list_profile_languages,
    read_reply_language,
    replace_profile_languages,
)
from tests.dbio import put
from tests.factories import profile_row, vacancy_row


@pytest.mark.parametrize(
    ("vacancy_language", "expected"),
    [
        pytest.param("Español", "Español", id="язык вакансии известен"),
        pytest.param(None, "Қазақша", id="неизвестен — язык человека"),
    ],
)
async def test_the_reply_language_comes_from_the_vacancy_and_the_person(
    session, session_factory, vacancy_language, expected
):
    """Язык отклика решает приложение по вакансии и анкете: язык вакансии, а
    неизвестен он — родной язык человека."""
    person = profile_row()
    await put(session_factory, person)
    await put(session_factory, ProfileLanguage(profile_id=person.id, language="Қазақша", level="native"))
    vacancy = vacancy_row(language=vacancy_language)
    await put(session_factory, vacancy)

    assert await read_reply_language(session, vacancy.id) == expected


async def test_an_empty_database_has_no_languages(session):
    """На пустой базе языков нет, и это не ошибка."""
    assert await list_profile_languages(session) == []


async def test_languages_are_listed_in_the_order_they_were_added(
    session, session_factory
):
    """Языки отдаются в порядке заведения — этот порядок задаёт пользователь."""
    profile = profile_row()
    await put(session_factory, profile)

    await replace_profile_languages(
        session,
        profile.id,
        [("Русский", "native"), ("Английский", "B2"), ("Армянский", "A2")],
    )

    got = await list_profile_languages(session)
    assert [(lang.language, lang.level) for lang in got] == [
        ("Русский", "native"),
        ("Английский", "B2"),
        ("Армянский", "A2"),
    ]


async def test_replacing_languages_wipes_the_previous_set(session, session_factory):
    """Замена стирает прежний набор целиком, а не дополняет его.

    Полная замена держит запрет «один язык дважды» сама: список из единиц
    строк, и сверять его построчно незачем.
    """
    profile = profile_row()
    await put(session_factory, profile)
    await replace_profile_languages(
        session, profile.id, [("Русский", "native"), ("Английский", "B1")]
    )

    await replace_profile_languages(session, profile.id, [("Английский", "C1")])

    got = await list_profile_languages(session)
    assert [(lang.language, lang.level) for lang in got] == [("Английский", "C1")]


async def test_replacing_with_nothing_clears_the_set(session, session_factory):
    """Замена пустым списком стирает все языки."""
    profile = profile_row()
    await put(session_factory, profile)
    await replace_profile_languages(session, profile.id, [("Русский", "native")])

    await replace_profile_languages(session, profile.id, [])

    assert await list_profile_languages(session) == []
