"""Сборка текстового блока анкеты для наставления модели.

Хранением анкеты занимается сосед — `repository/profile.py`; здесь её только
читают и складывают в текст, который уходит в наставление письма-отклика.
"""

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from backend.repository.profile import (
    get_profile,
    list_experience,
    list_skills,
)


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


def _years_in_it(experiences: list) -> int:
    """Сколько лет опыта — от самого раннего места работы до сегодня.

    Считается по началу, а не по сумме сроков: перерывы между местами опытом
    быть не перестают, а вычесть их значило бы спорить с тем, как этот срок
    называют в резюме. Отрицательным не бывает: место, начатое «завтра», —
    опечатка, а не отрицательный стаж.
    """
    min_start = min(e.start_date for e in experiences)
    today = date.today()
    years = today.year - min_start.year - (
        (today.month, today.day) < (min_start.month, min_start.day)
    )
    return max(years, 0)


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
        lines.append(f"Опыт: {_years_in_it(experiences)}+ лет в IT")
    return lines


def _experience_lines(experiences: list) -> list[str]:
    """Места работы строками; у каждого — одно достижение, если оно есть.

    Достижение берётся первое: в письмо уходит не весь список, а зацепка, и
    остальные только раздували бы наставление.
    """
    lines = []
    for e in experiences:
        end = e.end_date.strftime("%m.%Y") if e.end_date else "настоящее время"
        start = e.start_date.strftime("%m.%Y")
        suffix = f": {e.achievements[0]}" if e.achievements else ""
        lines.append(f"- {e.company} ({e.role}, {start} — {end}){suffix}")
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
