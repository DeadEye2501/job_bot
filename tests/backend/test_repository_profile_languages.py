"""Следствия замены списка языков профиля.

Языки заменяются целиком: их единицы, и полная замена держит запрет «один
язык дважды» сама собой — сверять список построчно незачем.
"""

from backend.repository.profile import list_profile_languages, replace_profile_languages
from tests.dbio import put
from tests.factories import profile_row


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
