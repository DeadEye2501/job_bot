"""Следствия разбора навыков и опыта работы в `backend/cv_parser.py`.

Проверяется через `parse_cv`: «модель вернула такой JSON — вышло такое».
Значения уровней и дат сняты прогоном настоящих функций.
"""

from datetime import date

import pytest

from backend.cv_parser import parse_cv
from tests.fakes.llm import CHAT, chat_json, provider


REQUIRED = {
    "first_name": "Алексей",
    "last_name": "Фролов",
    "title": "Python-разработчик",
    "email": "a@b.c",
}


async def parse_sections(**sections):
    """Прогнать ответ модели с заданными разделами через настоящий разбор."""
    client = provider({CHAT: chat_json({"profile": REQUIRED, **sections})})
    return await parse_cv("резюме", client, "qwen")


async def one_skill(**fields):
    """Разобрать единственный навык и вернуть его."""
    parsed = await parse_sections(skills=[{"name": "Python", **fields}])
    if not parsed.skills:
        raise AssertionError("навык не пережил разбор: parsed.skills пуст")
    return parsed.skills[0]


async def one_job(**fields):
    """Разобрать единственное место работы и вернуть его."""
    base = {"company": "ООО Ромашка", "role": "Разработчик", "start_date": "2020-03-01"}
    parsed = await parse_sections(experience=[{**base, **fields}])
    if not parsed.experience:
        raise AssertionError("место работы не пережило разбор: parsed.experience пуст")
    return parsed.experience[0]


@pytest.mark.parametrize(
    "raw, expected",
    [(5, 5), (9, 5), (0, 1), (-2, 1), (4.7, 4), ("4", 4), ("-3", 1)],
)
async def test_a_skill_level_is_clamped_into_the_scale(raw, expected):
    """Уровень навыка вгоняется в шкалу от единицы до пятёрки."""
    assert (await one_skill(level=raw)).level == expected


@pytest.mark.parametrize("raw", [True, False, None, "много", {"уровень": 5}])
async def test_an_unusable_skill_level_falls_back_to_the_middle(raw):
    """Негодный уровень заменяется серединой шкалы, а не роняет разбор."""
    assert (await one_skill(level=raw)).level == 3


async def test_a_skill_without_a_level_gets_the_middle():
    """Отсутствие уровня — тоже середина."""
    assert (await one_skill()).level == 3


async def test_a_skill_without_a_name_is_dropped():
    """Навык без названия не попадает в разбор."""
    parsed = await parse_sections(skills=[{"category": "Языки", "level": 5}])

    assert parsed.skills == []


async def test_a_skill_without_a_category_lands_in_the_general_one():
    """Навык без раздела попадает в общий."""
    assert (await one_skill()).category == "Общее"


async def test_an_alias_repeating_the_name_is_dropped():
    """Псевдоним, повторяющий название, псевдонимом не считается."""
    skill = await one_skill(name="PostgreSQL", aliases=["Postgres", "postgresql"])

    assert skill.aliases == ["Postgres"]


async def test_repeated_aliases_are_kept_once():
    """Повторяющиеся псевдонимы не удваиваются."""
    skill = await one_skill(aliases=["py", "PY", "Py"])

    assert skill.aliases == ["py"]


async def test_blank_and_non_string_aliases_are_dropped():
    """Мусор в псевдонимах отбрасывается."""
    skill = await one_skill(aliases=["py", "", "   ", 42, None])

    assert skill.aliases == ["py"]


async def test_a_skill_that_is_not_an_object_is_dropped():
    """Не объект вместо навыка отбрасывается, а не роняет разбор."""
    parsed = await parse_sections(skills=["Python", None, {"name": "Django"}])

    assert [s.name for s in parsed.skills] == ["Django"]


async def test_a_job_that_is_not_an_object_is_dropped():
    """Не объект вместо места работы отбрасывается, а не роняет разбор."""
    parsed = await parse_sections(experience=[
        "ООО Ромашка",
        None,
        {"company": "ООО Ромашка", "role": "Разработчик", "start_date": "2020-03-01"},
    ])

    assert [e.company for e in parsed.experience] == ["ООО Ромашка"]


async def test_a_full_date_is_taken_as_is():
    """Полная дата берётся как есть."""
    assert (await one_job(start_date="2020-03-17")).start_date == date(2020, 3, 17)


async def test_a_year_and_month_become_the_first_day():
    """Год с месяцем превращаются в первое число."""
    assert (await one_job(start_date="2020-03")).start_date == date(2020, 3, 1)


async def test_a_bare_year_becomes_the_first_of_january():
    """Голый год превращается в первое января."""
    assert (await one_job(start_date="2020")).start_date == date(2020, 1, 1)


@pytest.mark.parametrize("raw", ["2020-13", "2020-02-30", "февраль", "", None])
async def test_a_job_with_an_unusable_start_date_is_dropped(raw):
    """Место работы без разборчивой даты начала не попадает в разбор."""
    parsed = await parse_sections(experience=[{
        "company": "ООО Ромашка", "role": "Разработчик", "start_date": raw,
    }])

    assert parsed.experience == []


async def test_a_missing_end_date_means_still_working_there():
    """Отсутствие даты окончания означает, что работа продолжается."""
    assert (await one_job(end_date=None)).end_date is None


async def test_an_unusable_end_date_is_treated_as_absent():
    """Неразборчивая дата окончания приравнивается к отсутствию."""
    assert (await one_job(end_date="когда-то")).end_date is None


@pytest.mark.parametrize("missing", ["company", "role"])
async def test_a_job_without_a_company_or_a_role_is_dropped(missing):
    """Место работы без названия или должности не попадает в разбор."""
    base = {"company": "ООО Ромашка", "role": "Разработчик", "start_date": "2020-03-01"}
    del base[missing]

    assert (await parse_sections(experience=[base])).experience == []


async def test_bullets_are_trimmed_and_cleaned_of_rubbish():
    """Пункты списков подрезаются, мусор из них выпадает."""
    job = await one_job(
        achievements=["  Сократил время сборки  ", "", 42, None],
        responsibilities=["Поддерживал сервис"],
        stack=["Python", "  Docker  "],
    )

    assert job.achievements == ["Сократил время сборки"]
    assert job.responsibilities == ["Поддерживал сервис"]
    assert job.stack == ["Python", "Docker"]


async def test_the_order_of_jobs_is_preserved():
    """Порядок мест работы сохраняется таким, каким его дала модель."""
    parsed = await parse_sections(experience=[
        {"company": "Вторая", "role": "Р", "start_date": "2022"},
        {"company": "Первая", "role": "Р", "start_date": "2019"},
    ])

    assert [j.company for j in parsed.experience] == ["Вторая", "Первая"]
