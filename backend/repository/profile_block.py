"""Сборка текстового блока анкеты для наставления модели.

Хранением анкеты занимаются соседи — `repository/profile*.py`, по модулю на
предмет: поля, языки, навыки, места работы, проекты, резюме. Здесь её только
читают и складывают в текст, который уходит в наставление письма-отклика.
"""

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.tenure import place_period, years_in_it, years_text
from backend.llm.candidate import GENDER_WORDS
from backend.repository.profile import get_profile
from backend.repository.profile_experience import list_experience
from backend.repository.profile_projects import list_projects
from backend.repository.profile_skills import list_skills


def _skills_lines(skills: list) -> list[str]:
    """Навыки строками по разделам — по строке на раздел.

    Порядок разделов — порядок первого встреченного навыка: анкету человек
    заполняет сам, и переставлять его разделы своей волей незачем.
    """
    by_category: dict[str, list[str]] = {}
    for s in skills:
        by_category.setdefault(s.category, []).append(s.name)
    return [
        f"- {cat}: {', '.join(names)}" for cat, names in by_category.items()
    ]


def _header_lines(profile, experiences: list) -> list[str]:
    """Шапка блока: имя, роль, место, стаж.

    Незаполненные поля (None в БД) пропускаем целиком, иначе LLM получит
    «Имя: None None» / «Роль: None» и попытается включить это в письмо.
    """
    full_name = " ".join(
        p for p in (profile.first_name, profile.last_name) if p
    ).strip()
    lines: list[str] = []
    if full_name:
        lines.append(f"Имя: {full_name}")
    if profile.title:
        lines.append(f"Роль: {profile.title}")
    if profile.location:
        lines.append(f"Локация: {profile.location}")
    if profile.gender in GENDER_WORDS:
        lines.append(f"Пол: {GENDER_WORDS[profile.gender]}")
    if experiences:
        lines.append(f"Общий стаж: {years_text(years_in_it(experiences, date.today()))}")
    return lines


def _record_line(head: str, points: list[str]) -> str:
    """Запись анкеты строкой: её шапка и первый пункт, если он есть.

    Пункт берётся первый: в письмо уходит не весь список, а зацепка, и
    остальные только раздували бы наставление.
    """
    return f"- {head}: {points[0]}" if points else f"- {head}"


def _experience_lines(experiences: list) -> list[str]:
    return [
        _record_line(f"{e.company} ({e.role}, {place_period(e)})", e.achievements)
        for e in experiences
    ]


def _project_lines(projects: list) -> list[str]:
    """Проекты строками; у каждого — первый пункт «О проекте», обычно описание."""
    return [_record_line(p.name, p.about) for p in projects]


async def build_profile_block(session: AsyncSession) -> str:
    """Текстовый блок «Информация о кандидате» для cover-letter промпта.

    Собирает шапку, навыки по разделам, места работы и проекты. Если
    ``Profile.free_preferences`` заполнен — добавляется отдельной секцией
    «Дополнительно», чтобы LLM могла учесть пожелания (про релокацию, гео,
    специфичные предпочтения). Пустые части выпадают целиком: заголовок без
    содержимого модель приняла бы за потерянные данные.
    """
    profile = await get_profile(session)
    if profile is None:
        return ""
    skills = await list_skills(session)
    experiences = await list_experience(session)
    projects = await list_projects(session)

    sections: list[str] = []
    header_lines = _header_lines(profile, experiences)
    if header_lines:
        sections.append("\n".join(header_lines))
    skills_lines = _skills_lines(skills)
    if skills_lines:
        sections.append("Навыки:\n" + "\n".join(skills_lines))
    exp_lines = _experience_lines(experiences)
    if exp_lines:
        sections.append("Опыт работы:\n" + "\n".join(exp_lines))
    project_lines = _project_lines(projects)
    if project_lines:
        sections.append("Проекты:\n" + "\n".join(project_lines))
    if profile.free_preferences:
        sections.append(
            "Пожелания кандидата (в письмо — только то, о чём спрашивает вакансия):\n"
            + profile.free_preferences.strip()
        )
    return "\n\n".join(sections)
