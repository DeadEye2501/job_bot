"""Сборка текстового блока анкеты для наставления модели.

Хранением анкеты занимаются соседи — `repository/profile*.py`, по модулю на
предмет: поля, языки, навыки, места работы, резюме. Здесь её только читают и
складывают в текст, который уходит в наставление письма-отклика.
"""

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.tenure import place_period, years_in_it
from backend.repository.profile import get_profile
from backend.repository.profile_experience import list_experience
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
    if experiences:
        lines.append(f"Опыт: {years_in_it(experiences, date.today())}+ лет в IT")
    return lines


def _experience_lines(experiences: list) -> list[str]:
    """Места работы строками; у каждого — одно достижение, если оно есть.

    Достижение берётся первое: в письмо уходит не весь список, а зацепка, и
    остальные только раздували бы наставление.
    """
    lines = []
    for e in experiences:
        suffix = f": {e.achievements[0]}" if e.achievements else ""
        lines.append(f"- {e.company} ({e.role}, {place_period(e)}){suffix}")
    return lines


async def build_profile_block(session: AsyncSession) -> str:
    """Текстовый блок «Информация о кандидате» для cover-letter промпта.

    Собирает шапку, навыки по разделам и места работы. Если
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

    sections: list[str] = []
    header_lines = _header_lines(profile, experiences)
    if header_lines:
        sections.append("\n".join(header_lines))
    skills_lines = _skills_lines(skills)
    if skills_lines:
        sections.append("Стек:\n" + "\n".join(skills_lines))
    exp_lines = _experience_lines(experiences)
    if exp_lines:
        sections.append("Опыт работы:\n" + "\n".join(exp_lines))
    if profile.free_preferences:
        sections.append("Дополнительно:\n" + profile.free_preferences.strip())
    return "\n\n".join(sections)
