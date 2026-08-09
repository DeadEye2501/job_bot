"""Следствия чтения и записи основных полей профиля.

Профиль в базе один. Запись его заводит, если ещё нет, и правит иначе —
навыков и мест работы не касаясь: у тех свои пути записи.
"""

from backend.repository.profile import get_profile, load_profile_skills, upsert_profile
from tests.dbio import put
from tests.factories import profile_row, profile_skill_row


async def test_an_empty_database_has_no_profile(session):
    """На пустой базе профиля нет, и это не ошибка."""
    assert await get_profile(session) is None
    assert await load_profile_skills(session) == []


async def test_the_first_write_creates_the_profile(session):
    """Первая запись заводит профиль."""
    profile = await upsert_profile(
        session,
        first_name="Иван",
        last_name="Петров",
        title="Python-разработчик",
        email="ivan@example.com",
    )

    assert profile.id is not None
    assert (await get_profile(session)).first_name == "Иван"


async def test_a_later_write_edits_the_same_row(session, session_factory):
    """Повторная запись правит ту же строку, а не заводит вторую."""
    existing = profile_row(first_name="Иван", title="Разработчик")
    await put(session_factory, existing)

    profile = await upsert_profile(session, title="Старший разработчик")

    assert profile.id == existing.id
    assert profile.first_name == "Иван"
    assert profile.title == "Старший разработчик"


async def test_an_unnamed_field_is_left_untouched(session, session_factory):
    """Не названное в вызове поле остаётся прежним."""
    existing = profile_row(first_name="Иван", location="Москва", phone="+7")
    await put(session_factory, existing)

    await upsert_profile(session, location="Тбилиси")

    kept = await get_profile(session)
    assert kept.location == "Тбилиси"
    assert kept.first_name == "Иван"
    assert kept.phone == "+7"


async def test_writing_basics_does_not_touch_skills(session, session_factory):
    """Запись основных полей навыков не трогает — у них свой путь."""
    profile = profile_row()
    await put(session_factory, profile)
    await put(session_factory, profile_skill_row(profile.id, "Python"))

    await upsert_profile(session, title="Другая роль")

    assert [s.name for s in await load_profile_skills(session)] == ["Python"]
