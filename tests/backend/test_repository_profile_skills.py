"""Следствия сохранения списка навыков профиля.

Сохранение идёт по номерам строк, а не заменой всего списка: у навыка есть
связи с местами работы, и пересоздание строки их бы порвало. Строка с
известным номером правится на месте, без номера — заводится, а не названная в
присланном списке — удаляется вместе со связями.
"""

from sqlalchemy import select

from backend.models import ProfileSkill, profile_experience_skills
from backend.repository import list_skills, save_skills
from tests.dbio import put
from tests.factories import experience_row, profile_row, profile_skill_row


async def names_and_levels(session) -> list[tuple[str, int]]:
    """Навыки профиля в порядке выдачи."""
    return [(s.name, s.level) for s in await list_skills(session)]


async def test_skills_are_listed_in_the_order_they_were_added(
    session, session_factory
):
    """Навыки отдаются в порядке заведения — этот порядок задаёт пользователь.

    Присланный список нарочно идёт наоборот: порядок выдачи должен зависеть
    от того, когда строку завели, а не от того, в каком порядке её прислали
    в последний раз.
    """
    profile = profile_row()
    await put(session_factory, profile)
    early = profile_skill_row(profile.id, "Python", level=5)
    late = profile_skill_row(profile.id, "Docker", level=2)
    await put(session_factory, early, late)

    await save_skills(
        session,
        [
            {"id": late.id, "name": "Docker", "level": 2},
            {"id": early.id, "name": "Python", "level": 5},
        ],
        profile.id,
    )

    assert await names_and_levels(session) == [("Python", 5), ("Docker", 2)]


async def test_a_row_without_a_number_is_added(session, session_factory):
    """Строка без номера заводится новой."""
    profile = profile_row()
    await put(session_factory, profile)

    await save_skills(
        session,
        [{"name": "Python", "category": "backend", "level": 5, "aliases": ["py"]}],
        profile.id,
    )

    saved = (await session.scalars(select(ProfileSkill))).all()
    assert [(s.name, s.category, s.level, s.aliases) for s in saved] == [
        ("Python", "backend", 5, ["py"])
    ]


async def test_a_row_with_a_known_number_is_edited_in_place(
    session, session_factory
):
    """Строка с известным номером правится на месте, номер сохраняется.

    Именно на номере держатся связи с местами работы: пересоздай строку —
    и переименование навыка порвало бы их все.
    """
    profile = profile_row()
    await put(session_factory, profile)
    skill = profile_skill_row(profile.id, "Postgres", level=2)
    await put(session_factory, skill)

    await save_skills(
        session,
        [{"id": skill.id, "name": "PostgreSQL", "level": 4, "category": "базы"}],
        profile.id,
    )

    saved = (await session.scalars(select(ProfileSkill))).all()
    assert [(s.id, s.name, s.level) for s in saved] == [(skill.id, "PostgreSQL", 4)]


async def test_a_row_left_out_of_the_payload_is_removed(session, session_factory):
    """Строка, не названная в присланном списке, удаляется."""
    profile = profile_row()
    await put(session_factory, profile)
    kept = profile_skill_row(profile.id, "Python")
    dropped = profile_skill_row(profile.id, "Delphi")
    await put(session_factory, kept, dropped)

    await save_skills(session, [{"id": kept.id, "name": "Python"}], profile.id)

    assert [s.name for s in (await session.scalars(select(ProfileSkill))).all()] == [
        "Python"
    ]


async def test_removing_a_skill_takes_its_links_with_it(session, session_factory):
    """Удаление навыка уносит и его связи с местами работы.

    Связующая таблица сама по себе строки не чистит, и оставшаяся связь
    указывала бы в никуда.
    """
    profile = profile_row()
    await put(session_factory, profile)
    kept = profile_skill_row(profile.id, "Python")
    dropped = profile_skill_row(profile.id, "Delphi")
    await put(session_factory, kept, dropped)
    place = experience_row(profile.id)
    await put(session_factory, place)
    await session.execute(
        profile_experience_skills.insert().values(
            [
                {"experience_id": place.id, "skill_id": kept.id},
                {"experience_id": place.id, "skill_id": dropped.id},
            ]
        )
    )

    await save_skills(session, [{"id": kept.id, "name": "Python"}], profile.id)

    links = (
        await session.execute(select(profile_experience_skills.c.skill_id))
    ).scalars().all()
    assert list(links) == [kept.id]


async def test_renaming_a_skill_keeps_its_links_to_places(session, session_factory):
    """Переименование навыка связи с местами работы не рвёт.

    Ради этого сохранение и идёт по номерам строк: пересоздай строку при
    правке — и место работы потеряло бы навык от одной опечатки в названии.
    Проверено ревью: удаление навыка связи уносит, но это другая ветка, и о
    правке она ничего не говорила.
    """
    profile = profile_row()
    await put(session_factory, profile)
    skill = profile_skill_row(profile.id, "Postgres")
    await put(session_factory, skill)
    place = experience_row(profile.id)
    await put(session_factory, place)
    await session.execute(
        profile_experience_skills.insert().values(
            experience_id=place.id, skill_id=skill.id
        )
    )

    await save_skills(session, [{"id": skill.id, "name": "PostgreSQL"}], profile.id)

    links = (
        await session.execute(select(profile_experience_skills.c.skill_id))
    ).scalars().all()
    assert list(links) == [skill.id]
    saved = (await session.scalars(select(ProfileSkill))).all()
    assert [s.name for s in saved] == ["PostgreSQL"]


async def test_a_row_without_a_name_is_ignored(session, session_factory):
    """Строка без имени пропускается: безымянный навык ни с чем не совпадёт."""
    profile = profile_row()
    await put(session_factory, profile)

    await save_skills(
        session, [{"name": "   "}, {"name": "Python"}, {"name": None}], profile.id
    )

    assert [s.name for s in (await session.scalars(select(ProfileSkill))).all()] == [
        "Python"
    ]


async def test_missing_or_garbled_details_fall_back_to_defaults(
    session, session_factory
):
    """Не заданные и испорченные подробности заменяются умолчаниями.

    Список приходит с экрана, где поля правят руками: пустой уровень или
    буквы вместо числа не должны ронять сохранение всего списка.
    """
    profile = profile_row()
    await put(session_factory, profile)

    await save_skills(
        session,
        [
            {"name": "Без категории", "level": 3},
            {"name": "Пустая категория", "category": "   ", "level": 3},
            {"name": "Буквы вместо уровня", "level": "много"},
            {"name": "Пустой уровень", "level": None},
        ],
        profile.id,
    )

    saved = (await session.scalars(select(ProfileSkill))).all()
    assert [(s.name, s.category, s.level) for s in saved] == [
        ("Без категории", "Общее", 3),
        ("Пустая категория", "Общее", 3),
        ("Буквы вместо уровня", "Общее", 1),
        ("Пустой уровень", "Общее", 1),
    ]


async def test_only_real_strings_survive_among_the_spellings(
    session, session_factory
):
    """Среди написаний остаются только непустые строки."""
    profile = profile_row()
    await put(session_factory, profile)

    await save_skills(
        session,
        [{"name": "Python", "aliases": ["py", "   ", "", 42, None, "питон"]}],
        profile.id,
    )

    saved = (await session.scalars(select(ProfileSkill))).all()
    assert saved[0].aliases == ["py", "питон"]


async def test_an_unknown_number_starts_a_new_row(session, session_factory):
    """Незнакомый номер заводит новую строку, а не роняет сохранение.

    Экран мог прислать номер строки, которую тем временем удалили из другой
    вкладки.
    """
    profile = profile_row()
    await put(session_factory, profile)

    await save_skills(session, [{"id": 10_000, "name": "Python"}], profile.id)

    saved = (await session.scalars(select(ProfileSkill))).all()
    assert [(s.id, s.name) for s in saved] == [(saved[0].id, "Python")]
    assert saved[0].id != 10_000
