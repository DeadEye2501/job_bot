"""Следствия записи разобранного резюме в профиль.

Запись полная, а не по частям: мастер первого запуска подразумевает свежее
начало, и слияние оставило бы прежние навыки висеть рядом с новыми. Путь к
файлу резюме сохраняется той же записью — иначе сбой между двумя записями
оставил бы разобранный профиль без указания на источник.
"""

from datetime import date

import pytest
from sqlalchemy import select

from backend.payloads import ParsedCvLanguage
from backend.models import (
    AppSetting,
    Profile,
    ProfileExperience,
    ProfileLanguage,
    ProfileSkill,
    profile_experience_skills,
)
from backend.repository.profile import get_profile
from backend.repository.profile_cv import save_parsed_cv
from backend.repository.profile_experience import list_experience
from backend.repository.profile_skills import list_skills
from tests.dbio import put
from tests.factories import (
    experience_row,
    parsed_cv,
    parsed_cv_place,
    parsed_cv_profile,
    parsed_cv_skill,
    profile_row,
    profile_skill_row,
)


async def test_the_previous_profile_is_wiped_not_merged(session, session_factory):
    """Прежний профиль стирается целиком, а не сливается с новым.

    Иначе навыки из старого резюме висели бы рядом с новыми, и отличить их
    было бы нечем.

    Заполнено всё пять таблиц, которые запись стирает: профиль, языки,
    навыки, места работы и связи между двумя последними. Проверено ревью:
    без языков и связей два из пяти стираний удалялись бы незаметно.
    """
    old = profile_row(first_name="Былой", email="old@example.com")
    await put(session_factory, old)
    skill = profile_skill_row(old.id, "Delphi")
    place = experience_row(old.id, company="Прошлое место")
    await put(
        session_factory,
        skill,
        place,
        ProfileLanguage(profile_id=old.id, language="Латынь", level="native"),
    )
    await session.execute(
        profile_experience_skills.insert().values(
            experience_id=place.id, skill_id=skill.id
        )
    )

    await save_parsed_cv(session, parsed_cv())

    assert [p.first_name for p in (await session.scalars(select(Profile))).all()] == [
        "Иван"
    ]
    assert [s.name for s in await list_skills(session)] == []
    assert [e.company for e in await list_experience(session)] == []
    assert (await session.scalars(select(ProfileLanguage))).all() == []
    assert (
        await session.execute(select(profile_experience_skills.c.skill_id))
    ).scalars().all() == []


async def test_every_profile_field_reaches_the_row(session):
    """Все поля разобранного профиля доходят до строки."""
    await save_parsed_cv(
        session,
        parsed_cv(
            profile=parsed_cv_profile(
                phone="+79991234567",
                location="Тбилиси",
                telegram_username="ivan",
                github_url="https://github.com/ivan",
                education="МГУ",
                work_format=["remote", "hybrid"],
                grades=["senior"],
                free_preferences="готов к переезду",
            )
        ),
    )

    saved = await get_profile(session)
    assert saved.phone == "+79991234567"
    assert saved.location == "Тбилиси"
    assert saved.telegram_username == "ivan"
    assert saved.github_url == "https://github.com/ivan"
    assert saved.education == "МГУ"
    assert saved.work_format == ["remote", "hybrid"]
    assert saved.grades == ["senior"]
    assert saved.free_preferences == "готов к переезду"


async def test_languages_and_skills_are_written_with_the_profile(session):
    """Языки и навыки записываются вместе с профилем и привязаны к нему."""
    await save_parsed_cv(
        session,
        parsed_cv(
            languages=[
                ParsedCvLanguage(language="Русский", level="native"),
                ParsedCvLanguage(language="Английский", level="B2"),
            ],
            skills=[parsed_cv_skill("Python", level=5, aliases=["py"])],
        ),
    )

    profile = await get_profile(session)
    languages = (await session.scalars(select(ProfileLanguage))).all()
    skills = (await session.scalars(select(ProfileSkill))).all()

    assert [(x.language, x.level, x.profile_id) for x in languages] == [
        ("Русский", "native", profile.id),
        ("Английский", "B2", profile.id),
    ]
    assert [(s.name, s.level, s.aliases, s.profile_id) for s in skills] == [
        ("Python", 5, ["py"], profile.id)
    ]


async def test_a_place_is_linked_to_the_skills_it_names(session):
    """Место работы связывается с навыками, названными в его стеке."""
    await save_parsed_cv(
        session,
        parsed_cv(
            skills=[parsed_cv_skill("PostgreSQL", aliases=["Postgres"]), parsed_cv_skill("Python")],
            experience=[parsed_cv_place(stack=["Python", "Postgres"])],
        ),
    )

    places = await list_experience(session)
    assert sorted(s.name for s in places[0].skills) == ["PostgreSQL", "Python"]


@pytest.mark.parametrize(
    "written",
    ["docker-compose", "docker_compose", "docker/compose", "docker.compose"],
)
async def test_a_stack_item_is_matched_loosely(session, written):
    """Название из стека сопоставляется без учёта регистра и разделителей.

    Разделители названы поимённо: точка нужна «Node.js», косая черта —
    «CI/CD», подчёркивание приезжает из машинных выгрузок. Одного дефиса
    мало — правило обещает все четыре.
    """
    await save_parsed_cv(
        session,
        parsed_cv(
            skills=[parsed_cv_skill("Docker Compose")],
            experience=[parsed_cv_place(stack=[written])],
        ),
    )

    places = await list_experience(session)
    assert [s.name for s in places[0].skills] == ["Docker Compose"]


async def test_an_unknown_stack_item_is_dropped(session):
    """Название из стека, которому не нашлось навыка, связи не даёт.

    Разбор мог назвать в опыте то, чего нет в списке навыков, — терять из-за
    этого всё место работы незачем.

    Второй заведённый навык, в стеке не названный, отличает «связались
    названные» от «связались все подряд».
    """
    await save_parsed_cv(
        session,
        parsed_cv(
            skills=[parsed_cv_skill("Python"), parsed_cv_skill("Docker")],
            experience=[parsed_cv_place(stack=["Python", "Кобол"])],
        ),
    )

    places = await list_experience(session)
    assert [s.name for s in places[0].skills] == ["Python"]


async def test_a_place_keeps_all_it_was_given(session):
    """Место работы сохраняется со всем, что при нём разобрано."""
    await save_parsed_cv(
        session,
        parsed_cv(
            experience=[
                parsed_cv_place(
                    company="Контур",
                    company_url="https://kontur.ru",
                    role="Старший",
                    start_date=date(2020, 3, 1),
                    end_date=date(2023, 6, 30),
                    achievements=["ускорил сборку"],
                    responsibilities=["правил ошибки"],
                )
            ]
        ),
    )

    saved = (await session.scalars(select(ProfileExperience))).all()[0]
    assert saved.company_url == "https://kontur.ru"
    assert saved.start_date == date(2020, 3, 1)
    assert saved.end_date == date(2023, 6, 30)
    assert saved.achievements == ["ускорил сборку"]
    assert saved.responsibilities == ["правил ошибки"]


async def test_the_path_to_the_file_is_recorded_alongside(session):
    """Путь к файлу резюме записывается той же записью."""
    await save_parsed_cv(session, parsed_cv(), cv_path="cv/ivan.pdf")

    saved = await session.get(AppSetting, "cv_path")
    assert saved.value == "cv/ivan.pdf"


async def test_a_recorded_path_is_replaced_not_doubled(session):
    """Повторная запись заменяет прежний путь, а не заводит вторую настройку."""
    await save_parsed_cv(session, parsed_cv(), cv_path="cv/старое.pdf")

    await save_parsed_cv(session, parsed_cv(), cv_path="cv/новое.pdf")

    rows = (await session.scalars(select(AppSetting))).all()
    assert [(r.key, r.value) for r in rows] == [("cv_path", "cv/новое.pdf")]


async def test_without_a_path_nothing_is_recorded(session):
    """Без пути к файлу настройка не заводится."""
    await save_parsed_cv(session, parsed_cv())

    assert (await session.scalars(select(AppSetting))).all() == []
