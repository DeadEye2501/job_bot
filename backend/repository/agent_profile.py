"""Анкета человека целиком, как её видит агент: со стажем общим и по навыкам."""

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.salary import salary_text
from backend.domain.tenure import place_period, skill_years, years_in_it
from backend.llm.candidate import candidate_languages, format_languages
from backend.models import Gender, SalaryPeriod
from backend.repository.profile import get_profile
from backend.repository.profile_experience import list_experience
from backend.repository.profile_languages import list_profile_languages
from backend.repository.profile_skills import list_skills

_GENDER = {Gender.MALE: "мужской", Gender.FEMALE: "женский"}
_PERIOD = {SalaryPeriod.HOUR: "в час", SalaryPeriod.MONTH: "в месяц", SalaryPeriod.YEAR: "в год"}


async def build_agent_profile(session: AsyncSession, today: date) -> str:
    """Анкета для агента. Пустые поля названы пустыми: агенту видно, что их нет."""
    profile = await get_profile(session)
    if profile is None:
        return ""
    places = await list_experience(session)
    skills = await list_skills(session)
    languages = await list_profile_languages(session)
    return "\n".join([
        *_person_lines(profile, languages),
        f"Общий стаж: {_years(years_in_it(places, today)) if places else 'нет мест работы'}",
        "Навыки:", *_skill_lines(skills, places, today),
        "Опыт работы:", *_place_lines(places),
        f"Предпочтения: {profile.free_preferences or 'не указаны'}",
    ])


def _person_lines(p, languages) -> list[str]:
    spoken = format_languages(candidate_languages(languages))
    return [
        f"Имя: {p.first_name}",
        f"Фамилия: {p.last_name}",
        f"Имя латиницей: {p.first_name_latin or 'не указано'}",
        f"Фамилия латиницей: {p.last_name_latin or 'не указана'}",
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
        f"Образование: {p.education or 'не указано'}",
        f"Ожидаемая зарплата: {_salary(p)}",
    ]


def _salary(p) -> str:
    if p.expected_salary is None:
        return "не указана"
    amount = p.expected_salary
    money = salary_text(amount, amount, p.expected_salary_currency or "валюта не указана")
    period = _PERIOD.get(p.expected_salary_period, "период не указан")
    return f"{money} {period}, на руки"


def _skill_lines(skills, places, today: date) -> list[str]:
    lines = []
    for skill in skills:
        named = [p for p in places if skill in p.skills]
        term = f"стаж {_years(skill_years(named, today))}" if named else (
            "стаж не привязан к местам работы"
        )
        lines.append(f"- {skill.name} — уровень {skill.level}, {term}")
    return lines


def _place_lines(places) -> list[str]:
    lines = []
    for p in places:
        lines.append(f"- {p.company}, {p.role}, {place_period(p)}")
        lines += [f"  Обязанность: {one}" for one in p.responsibilities]
        lines += [f"  Достижение: {one}" for one in p.achievements]
    return lines


def _years(years: int) -> str:
    return f"{years}+ г."
