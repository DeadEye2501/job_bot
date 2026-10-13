"""Разобранное резюме — то, что разбор отдаёт записи анкеты и сверке с текстом.

Умолчания берутся у строк анкеты (`tests/factories.py`): разобранное и
записанное описывают одного человека, и проверка «разобранное легло в анкету»
иначе сравнивала бы двух разных.
"""

from backend.payloads import (
    ParsedCv,
    ParsedCvExperience,
    ParsedCvProfile,
    ParsedCvProject,
    ParsedCvSkill,
)
from tests.factories import experience_fields, person_fields, project_fields, skill_fields


def parsed_cv_profile(**overrides) -> ParsedCvProfile:
    """Разобранный профиль: обязательное заполнено, остальное пусто.

    Тот же человек, что и в строке анкеты, — иначе проверка «разобранное легло
    в анкету» сравнивала бы двух разных.
    """
    fields = person_fields(
        phone=None,
        location=None,
        telegram_username=None,
        github_url=None,
        education=None,
        work_format=[],
        grades=[],
        free_preferences=None,
        expected_salary=None,
        expected_salary_currency=None,
        expected_salary_period=None,
        first_name_latin=None,
        last_name_latin=None,
        gender=None,
    )
    fields.update(overrides)
    return ParsedCvProfile(**fields)


def parsed_cv_skill(name: str, **overrides) -> ParsedCvSkill:
    """Разобранный навык — с теми же умолчаниями, что и строка в базе."""
    return ParsedCvSkill(name=name, **skill_fields(**overrides))


def parsed_cv_place(**overrides) -> ParsedCvExperience:
    """Разобранное место работы — с теми же умолчаниями, что и строка в базе.

    Своё поле здесь одно: стек места работы разбор из резюме приносит, а
    колонки под него нет.
    """
    fields = experience_fields(stack=[])
    fields.update(overrides)
    return ParsedCvExperience(**fields)


def parsed_cv_project(**overrides) -> ParsedCvProject:
    """Разобранный проект — с теми же умолчаниями, что и строка в базе, и стеком."""
    return ParsedCvProject(**project_fields(**{"stack": [], **overrides}))


def parsed_cv(**overrides) -> ParsedCv:
    """Разобранное резюме целиком."""
    fields = {
        "profile": parsed_cv_profile(),
        "languages": [],
        "skills": [],
        "experience": [],
        "projects": [],
    }
    fields.update(overrides)
    return ParsedCv(**fields)
