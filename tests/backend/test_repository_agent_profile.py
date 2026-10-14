"""Анкета для агента: всё, на что опираются промпты, со стажем от кода."""

import re
from datetime import date

from backend.llm.rules import LATIN_NAME_RULE
from backend.models import (
    Gender,
    ProfileLanguage,
    SalaryPeriod,
    profile_experience_skills,
    profile_project_skills,
)
from backend.repository.agent_profile import build_agent_profile
from tests.dbio import put
from tests.factories import experience_row, profile_row, profile_skill_row, project_row
from tests.fakes.agent import TODAY


async def _person(session_factory, **fields):
    person = profile_row(**fields)
    await put(session_factory, person)
    return person


async def test_no_profile_gives_nothing(session):
    assert await build_agent_profile(session, TODAY, photo=False) == ""


async def test_the_answers_for_forms_reach_the_agent(session, session_factory):
    await _person(
        session_factory, first_name_latin="Ivan", last_name_latin="Petrov",
        gender=Gender.MALE, expected_salary=250000, expected_salary_currency="RUB",
        expected_salary_period=SalaryPeriod.MONTH,
    )

    text = await build_agent_profile(session, TODAY, photo=False)

    assert "Имя латиницей: Ivan" in text and "Фамилия латиницей: Petrov" in text
    assert "мужской" in text
    assert "250000 RUB в месяц, на руки" in text


async def test_the_name_rule_points_at_both_spellings_of_the_profile(session, session_factory):
    """Имя пишется алфавитом текста: русскому письму — поля «Имя» и «Фамилия»,
    тексту латиницей — латинские. Правило отсылает только к полям, что в анкете есть."""
    await _person(session_factory)
    text = await build_agent_profile(session, TODAY, photo=False)
    labels = {line.split(":")[0].strip() for line in text.splitlines()}
    named = set(re.findall(r"«([^»]+)»", LATIN_NAME_RULE))

    assert {
        "Имя", "Фамилия", "Отчество", "Имя латиницей", "Фамилия латиницей", "Отчество латиницей",
    } <= named <= labels


async def test_empty_answers_are_named_empty(session, session_factory):
    """Пустое поле видно агенту пустым, а не пропавшим."""
    await _person(session_factory)

    text = await build_agent_profile(session, TODAY, photo=False)

    assert "Пол: не указан" in text
    assert "Ожидаемая зарплата: не указана" in text
    for line in ("Отчество: не указано", "Отчество латиницей: не указано",
                 "Дата рождения: не указана", "Гражданство: не указано",
                 "Ссылка на резюме: не указана", "О себе: не указано", "Фото: нет"):
        assert line in text


async def test_the_new_personal_fields_reach_the_agent(session, session_factory):
    await _person(
        session_factory, patronymic="Сергеевич", patronymic_latin="Sergeevich",
        birth_date=date(1990, 3, 15), citizenship="Россия",
        resume_url="https://hh.ru/resume/1", about_me="Строю сервисы.",
    )

    text = await build_agent_profile(session, TODAY, photo=False)

    for line in ("Отчество: Сергеевич", "Отчество латиницей: Sergeevich",
                 "Дата рождения: 15.03.1990", "Возраст (полных лет): 36",
                 "Гражданство: Россия", "Ссылка на резюме: https://hh.ru/resume/1",
                 "О себе: Строю сервисы."):
        assert line in text


async def test_the_age_grows_only_on_the_birthday(session, session_factory):
    """Возраст считает код: день рождения завтра — полных лет ещё прежнее число."""
    await _person(session_factory, birth_date=date(1990, 10, 10))

    before = await build_agent_profile(session, date(2026, 10, 9), photo=False)
    on_the_day = await build_agent_profile(session, date(2026, 10, 10), photo=False)

    assert "Возраст (полных лет): 35" in before
    assert "Возраст (полных лет): 36" in on_the_day


async def test_a_photo_the_agent_can_attach_is_named_present(session, session_factory):
    await _person(session_factory)

    assert "Фото: есть" in await build_agent_profile(session, TODAY, photo=True)


async def test_a_skill_gets_the_tenure_of_the_places_that_name_it(
    session, session_factory
):
    person = await _person(session_factory)
    tool = profile_skill_row(person.id, "Инструмент-А")
    loose = profile_skill_row(person.id, "Инструмент-Б")
    first = experience_row(person.id, company="Первое", start_date=date(2019, 1, 1),
                           end_date=date(2021, 1, 1))
    second = experience_row(person.id, company="Второе", start_date=date(2022, 1, 1),
                            end_date=date(2023, 1, 1))
    await put(session_factory, tool, loose, first, second)
    await session.execute(profile_experience_skills.insert().values([
        {"experience_id": first.id, "skill_id": tool.id},
        {"experience_id": second.id, "skill_id": tool.id},
    ]))
    await session.commit()

    text = await build_agent_profile(session, TODAY, photo=False)

    assert "Инструмент-А — уровень 3, стаж 4+ г." in text
    assert "Инструмент-Б — уровень 3, стаж не привязан к местам работы" in text
    assert "Общий стаж: 7+ г." in text


async def test_a_place_of_work_comes_whole(session, session_factory):
    """Обязанности и все достижения, а не первое."""
    person = await _person(session_factory)
    await put(session_factory, experience_row(
        person.id, company="Место", role="Роль", start_date=date(2020, 3, 1), end_date=None,
        responsibilities=["вела учёт"], achievements=["первое", "второе"],
    ))

    text = await build_agent_profile(session, TODAY, photo=False)

    assert "Место, Роль, 03.2020 — настоящее время" in text
    assert "вела учёт" in text and "первое" in text and "второе" in text


async def test_a_project_comes_whole_with_its_link(session, session_factory):
    """Проект целиком, как место работы, — и со ссылкой: формы её спрашивают."""
    person = await _person(session_factory)
    await put(session_factory, project_row(
        person.id, name="Бот", url="https://example.org/bot", about=["Описание", "Пункт"]))

    text = await build_agent_profile(session, TODAY, photo=False)

    assert "- Бот, https://example.org/bot" in text
    assert "О проекте: Описание" in text and "О проекте: Пункт" in text


async def test_a_project_without_a_link_names_no_link(session, session_factory):
    """Нет ссылки — нет и слова о ней: агент вписал бы его в поле формы."""
    person = await _person(session_factory)
    await put(session_factory, project_row(person.id, name="Бот", url=None))

    text = await build_agent_profile(session, TODAY, photo=False)

    assert "- Бот\n" in text
    assert "None" not in text


async def test_a_skill_in_a_place_and_a_project_keeps_the_places_tenure(
    session, session_factory
):
    """Стаж — по местам работы, и проект его не отменяет."""
    person = await _person(session_factory)
    tool = profile_skill_row(person.id, "Инструмент-Г")
    place = experience_row(person.id, start_date=date(2019, 1, 1), end_date=date(2021, 1, 1))
    project = project_row(person.id)
    await put(session_factory, tool, place, project)
    await session.execute(profile_experience_skills.insert().values(
        experience_id=place.id, skill_id=tool.id))
    await session.execute(profile_project_skills.insert().values(
        project_id=project.id, skill_id=tool.id))
    await session.commit()

    text = await build_agent_profile(session, TODAY, photo=False)

    assert "Инструмент-Г — уровень 3, стаж 2+ г." in text


async def test_a_skill_named_only_in_projects_is_had_without_tenure(session, session_factory):
    """Опыт с инструментом проект подтверждает, но стажа не даёт."""
    person = await _person(session_factory)
    tool = profile_skill_row(person.id, "Инструмент-В")
    project = project_row(person.id)
    await put(session_factory, tool, project)
    await session.execute(profile_project_skills.insert().values(
        project_id=project.id, skill_id=tool.id))
    await session.commit()

    text = await build_agent_profile(session, TODAY, photo=False)

    assert "Инструмент-В — уровень 3, опыт есть в проектах, стаж не считается" in text
    assert "Общий стаж: нет мест работы" in text


async def test_languages_come_with_their_levels(session, session_factory):
    person = await _person(session_factory)
    await put(session_factory, ProfileLanguage(profile_id=person.id, language="Испанский", level="B2"))

    assert "Испанский — B2" in await build_agent_profile(session, TODAY, photo=False)
