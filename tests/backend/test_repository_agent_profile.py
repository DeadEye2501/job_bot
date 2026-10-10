"""Анкета для агента: всё, на что опираются промпты, со стажем от кода."""

import re
from datetime import date

from backend.llm.rules import LATIN_NAME_RULE
from backend.models import Gender, ProfileLanguage, SalaryPeriod, profile_experience_skills
from backend.repository.agent_profile import build_agent_profile
from tests.dbio import put
from tests.factories import experience_row, profile_row, profile_skill_row
from tests.fakes.agent import TODAY


async def _person(session_factory, **fields):
    person = profile_row(**fields)
    await put(session_factory, person)
    return person


async def test_no_profile_gives_nothing(session):
    assert await build_agent_profile(session, TODAY) == ""


async def test_the_answers_for_forms_reach_the_agent(session, session_factory):
    await _person(
        session_factory, first_name_latin="Ivan", last_name_latin="Petrov",
        gender=Gender.MALE, expected_salary=250000, expected_salary_currency="RUB",
        expected_salary_period=SalaryPeriod.MONTH,
    )

    text = await build_agent_profile(session, TODAY)

    assert "Имя латиницей: Ivan" in text and "Фамилия латиницей: Petrov" in text
    assert "мужской" in text
    assert "250000 RUB в месяц, на руки" in text


async def test_the_name_rule_points_at_both_spellings_of_the_profile(session, session_factory):
    """Имя пишется алфавитом текста: русскому письму — поля «Имя» и «Фамилия»,
    тексту латиницей — латинские. Правило отсылает только к полям, что в анкете есть."""
    await _person(session_factory)
    text = await build_agent_profile(session, TODAY)
    labels = {line.split(":")[0].strip() for line in text.splitlines()}
    named = set(re.findall(r"«([^»]+)»", LATIN_NAME_RULE))

    assert {"Имя", "Фамилия", "Имя латиницей", "Фамилия латиницей"} <= named <= labels


async def test_empty_answers_are_named_empty(session, session_factory):
    """Пустое поле видно агенту пустым, а не пропавшим."""
    await _person(session_factory)

    text = await build_agent_profile(session, TODAY)

    assert "Пол: не указан" in text
    assert "Ожидаемая зарплата: не указана" in text


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

    text = await build_agent_profile(session, TODAY)

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

    text = await build_agent_profile(session, TODAY)

    assert "Место, Роль, 03.2020 — настоящее время" in text
    assert "вела учёт" in text and "первое" in text and "второе" in text


async def test_languages_come_with_their_levels(session, session_factory):
    person = await _person(session_factory)
    await put(session_factory, ProfileLanguage(profile_id=person.id, language="Испанский", level="B2"))

    assert "Испанский — B2" in await build_agent_profile(session, TODAY)
