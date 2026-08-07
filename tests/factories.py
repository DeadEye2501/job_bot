"""Построение объектов, которые тесты подают на вход коду.

Здесь только то, что живёт в памяти: полезные нагрузки и строки моделей без
сессии. Настоящая запись в базу остаётся делом самих тестов — фабрика не
знает ни про сессию, ни про схему.
"""

from backend.models import ProfileSkill
from backend.payloads import ParsedVacancy

_EMPTY_VACANCY = {
    "title": "Python-разработчик",
    "description": None,
    "company_name": None,
    "company_website": None,
    "hr_contact": None,
    "other_contact": None,
    "stack_required": [],
    "stack_preferred": [],
    "grade": None,
    "salary": None,
    "remote": None,
    "location": None,
}


def parsed_vacancy(**overrides) -> ParsedVacancy:
    """Разобранная вакансия: заголовок есть, остальное пусто.

    Умолчание выбрано так, чтобы тест называл ровно те поля, которые
    проверяет: всё незаданное заведомо не влияет на результат.
    """
    return ParsedVacancy(**{**_EMPTY_VACANCY, **overrides})


def profile_skill(
    name: str, level: int, aliases: list | None = None
) -> ProfileSkill:
    """Навык профиля вне сессии — в базу не пишется, нужен как вход в подсчёт."""
    return ProfileSkill(
        name=name, level=level, aliases=aliases or [], category="backend"
    )
