"""Анкета человека целиком, как её видит агент: со стажем общим и по навыкам."""

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.salary import salary_text
from backend.domain.tenure import full_years, place_period, skill_years, years_in_it
from backend.llm.candidate import candidate_languages, format_languages
from backend.models import Gender, SalaryPeriod
from backend.repository.profile import get_profile
from backend.repository.profile_experience import list_experience
from backend.repository.profile_languages import list_profile_languages
from backend.repository.profile_projects import list_projects
from backend.repository.profile_skills import list_skills

_GENDER = {Gender.MALE: "мужской", Gender.FEMALE: "женский"}
_PERIOD = {SalaryPeriod.HOUR: "в час", SalaryPeriod.MONTH: "в месяц", SalaryPeriod.YEAR: "в год"}


async def build_agent_profile(session: AsyncSession, today: date, photo: bool) -> str:
    """Анкета для агента. Пустые поля названы пустыми: агенту видно, что их нет.

    Есть ли фото, решает зовущий тем же `photo_file`, что даёт файл инструменту:
    анкета и инструмент не должны расходиться в ответе.
    """
    profile = await get_profile(session)
    if profile is None:
        return ""
    places = await list_experience(session)
    projects = await list_projects(session)
    skills = await list_skills(session)
    languages = await list_profile_languages(session)
    return "\n".join([
        *_person_lines(profile, languages, today),
        f"Фото: {'есть' if photo else 'нет'}",
        f"Общий стаж: {_years(years_in_it(places, today)) if places else 'нет мест работы'}",
        "Навыки:", *_skill_lines(skills, places, projects, today),
        "Опыт работы:", *_place_lines(places),
        "Проекты:", *_project_lines(projects),
        f"О себе: {profile.about_me or 'не указано'}",
        f"Предпочтения: {profile.free_preferences or 'не указаны'}",
    ])


def _person_lines(p, languages, today: date) -> list[str]:
    spoken = format_languages(candidate_languages(languages))
    return [
        f"Имя: {p.first_name}",
        f"Фамилия: {p.last_name}",
        f"Отчество: {p.patronymic or 'не указано'}",
        f"Имя латиницей: {p.first_name_latin or 'не указано'}",
        f"Фамилия латиницей: {p.last_name_latin or 'не указана'}",
        f"Отчество латиницей: {p.patronymic_latin or 'не указано'}",
        *_birth_lines(p.birth_date, today),
        f"Гражданство: {p.citizenship or 'не указано'}",
        f"Пол: {_GENDER.get(p.gender, 'не указан')}",
        f"Должность: {p.title}",
        f"Грейды: {', '.join(p.grades) or 'не указаны'}",
        f"Формат работы: {', '.join(p.work_format) or 'не указан'}",
        f"Место: {p.location or 'не указано'}",
        f"Языки: {spoken}",
        f"Почта: {p.email}",
        f"Телефон: {p.phone or 'не указан'}",
        f"Telegram: {p.telegram_username or 'не указан'}",
        f"GitHub: {p.github_url or 'не указан'}",
        f"Ссылка на резюме: {p.resume_url or 'не указана'}",
        f"Образование: {p.education or 'не указано'}",
        f"Ожидаемая зарплата: {_salary(p)}",
    ]


def _birth_lines(born: date | None, today: date) -> list[str]:
    """Дата рождения и возраст — возраст считает код: модель в подсчёте лет ошибается."""
    if born is None:
        return ["Дата рождения: не указана"]
    return [f"Дата рождения: {born:%d.%m.%Y}", f"Возраст (полных лет): {full_years(born, today)}"]


def _salary(p) -> str:
    if p.expected_salary is None:
        return "не указана"
    amount = p.expected_salary
    money = salary_text(amount, amount, p.expected_salary_currency or "валюта не указана")
    period = _PERIOD.get(p.expected_salary_period, "период не указан")
    return f"{money} {period}, на руки"


def _skill_lines(skills, places, projects, today: date) -> list[str]:
    return [
        f"- {skill.name} — уровень {skill.level}, {_skill_term(skill, places, projects, today)}"
        for skill in skills
    ]


def _skill_term(skill, places, projects, today: date) -> str:
    """Стаж по навыку — только по местам работы; навык из одних проектов — опыт
    без стажа: проект показывает, что человек с инструментом работал, но срока
    не даёт."""
    named = [p for p in places if skill in p.skills]
    if named:
        return f"стаж {_years(skill_years(named, today))}"
    if any(skill in p.skills for p in projects):
        return "опыт есть в проектах, стаж не считается"
    return "стаж не привязан к местам работы"


def _record_lines(head: str, labelled: list[tuple[str, list[str]]]) -> list[str]:
    """Запись анкеты целиком: шапка и под ней каждый пункт со своей подписью."""
    return [f"- {head}", *(f"  {label}: {one}" for label, points in labelled for one in points)]


def _place_lines(places) -> list[str]:
    return [
        line for p in places for line in _record_lines(
            f"{p.company}, {p.role}, {place_period(p)}",
            [("Обязанность", p.responsibilities), ("Достижение", p.achievements)],
        )
    ]


def _project_lines(projects) -> list[str]:
    """Проекты целиком, как места работы, — и со ссылкой: формы её спрашивают."""
    return [
        line for p in projects for line in _record_lines(
            f"{p.name}, {p.url}" if p.url else p.name, [("О проекте", p.about)]
        )
    ]


def _years(years: int) -> str:
    return f"{years}+ г."
