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
    Gender,
    Profile,
    ProfileExperience,
    ProfileLanguage,
    ProfileSkill,
    SalaryPeriod,
    profile_experience_skills,
    profile_project_skills,
)
from backend.repository.profile import get_profile
from backend.repository.profile_cv import save_parsed_cv
from backend.repository.profile_experience import list_experience
from backend.repository.profile_projects import list_projects
from backend.repository.profile_skills import list_skills
from tests.dbio import put
from tests.factories import experience_row, profile_row, profile_skill_row, project_row
from tests.factories_cv import (
    parsed_cv,
    parsed_cv_place,
    parsed_cv_profile,
    parsed_cv_skill,
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


async def test_a_new_resume_wipes_the_previous_projects(session, session_factory):
    """Проекты стираются вместе с прежней анкетой, со связками стека: иначе
    навык и анкета, на которые они смотрят, не стёрлись бы вовсе."""
    old = profile_row()
    await put(session_factory, old)
    skill = profile_skill_row(old.id, "Delphi")
    project = project_row(old.id, name="Прошлый проект")
    await put(session_factory, skill, project)
    await session.execute(
        profile_project_skills.insert().values(project_id=project.id, skill_id=skill.id)
    )

    await save_parsed_cv(session, parsed_cv())

    assert await list_projects(session) == []
    assert (
        await session.execute(select(profile_project_skills.c.skill_id))
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


async def test_a_skill_named_twice_in_a_stack_is_linked_once(session):
    """Название и прозвище одного навыка в стеке — одна связь, а не две: вторая
    упала бы на первичном ключе связки и унесла весь разбор."""
    await save_parsed_cv(
        session,
        parsed_cv(
            skills=[parsed_cv_skill("PostgreSQL", aliases=["Postgres"])],
            experience=[parsed_cv_place(stack=["PostgreSQL", "Postgres"])],
        ),
    )

    places = await list_experience(session)
    assert [s.name for s in places[0].skills] == ["PostgreSQL"]


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


async def test_a_new_resume_keeps_the_answers_it_did_not_give(session, session_factory):
    """Повторный разбор без зарплаты и пола не стирает введённое человеком."""
    await put(session_factory, profile_row(
        expected_salary=300000, expected_salary_period=SalaryPeriod.MONTH,
        gender=Gender.FEMALE, first_name_latin="Anna",
    ))

    await save_parsed_cv(session, parsed_cv())

    p = (await session.scalars(select(Profile))).one()
    assert (p.expected_salary, p.expected_salary_period, p.gender, p.first_name_latin) == (
        300000, SalaryPeriod.MONTH, Gender.FEMALE, "Anna"
    )


async def test_a_new_resume_overrides_the_answers_it_gave(session, session_factory):
    await put(session_factory, profile_row(
        expected_salary=300000, gender=Gender.FEMALE, first_name_latin="Anna",
    ))

    await save_parsed_cv(session, parsed_cv(profile=parsed_cv_profile(
        expected_salary=350000, gender=Gender.MALE, first_name_latin="Ivan",
    )))

    p = (await session.scalars(select(Profile))).one()
    assert (p.expected_salary, p.gender, p.first_name_latin) == (350000, Gender.MALE, "Ivan")


async def test_a_new_salary_does_not_borrow_the_old_currency(session, session_factory):
    """Зарплата переносится связкой: новая сумма со старой валютой — чужая зарплата."""
    await put(session_factory, profile_row(
        expected_salary=300000, expected_salary_currency="₽",
        expected_salary_period=SalaryPeriod.MONTH,
    ))

    await save_parsed_cv(session, parsed_cv(profile=parsed_cv_profile(expected_salary=5000)))

    p = (await session.scalars(select(Profile))).one()
    assert (p.expected_salary, p.expected_salary_currency, p.expected_salary_period) == (
        5000, None, None
    )
