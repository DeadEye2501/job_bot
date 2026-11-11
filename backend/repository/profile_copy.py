"""Анкета активного профиля как разобранное резюме — чтобы новый профиль получил её копию.

Копия пишется тем же `save_parsed_cv`, что и разбор резюме: своего писателя
анкеты здесь нет, и устройство её строк знает одно место.
"""

from dataclasses import fields, replace

from sqlalchemy.ext.asyncio import AsyncSession

from backend.payloads import (
    ParsedCv,
    ParsedCvExperience,
    ParsedCvLanguage,
    ParsedCvPreference,
    ParsedCvProfile,
    ParsedCvProject,
    ParsedCvSkill,
)
from backend.repository.profile import get_profile
from backend.repository.profile_experience import list_experience
from backend.repository.profile_languages import list_profile_languages
from backend.repository.profile_preferences import list_profile_preferences
from backend.repository.profile_projects import list_projects
from backend.repository.profile_skills import list_skills


def _columns(row, kind: type) -> dict:
    """Поля разобранной записи, взятые из одноимённых колонок строки, — кроме стека."""
    return {f.name: getattr(row, f.name) for f in fields(kind) if f.name != "stack"}


async def profile_as_parsed(session: AsyncSession) -> ParsedCv | None:
    """Анкета активного профиля как разобранное резюме; `None` — анкеты нет.

    Стек мест работы и проектов — названиями навыков: по ним `save_parsed_cv`
    свяжет записи с навыками новой анкеты. Языка текста у анкеты нет: он нужен
    только разбору файла.
    """
    profile = await get_profile(session)
    if profile is None:
        return None
    return ParsedCv(
        profile=ParsedCvProfile(**_columns(profile, ParsedCvProfile)),
        languages=[
            ParsedCvLanguage(**_columns(lang, ParsedCvLanguage))
            for lang in await list_profile_languages(session)
        ],
        preferences=[
            ParsedCvPreference(**_columns(one, ParsedCvPreference))
            for one in await list_profile_preferences(session)
        ],
        skills=[ParsedCvSkill(**_columns(s, ParsedCvSkill)) for s in await list_skills(session)],
        experience=[
            ParsedCvExperience(**_columns(e, ParsedCvExperience), stack=[s.name for s in e.skills])
            for e in await list_experience(session)
        ],
        projects=[
            ParsedCvProject(**_columns(p, ParsedCvProject), stack=[s.name for s in p.skills])
            for p in await list_projects(session)
        ],
        text_language=None,
    )


def personal_part(parsed: ParsedCv) -> ParsedCv:
    """Только личные данные анкеты: ФИО и их латиница, пол, дата рождения,
    гражданство, email, телефон, город, Telegram, GitHub, LinkedIn и языки.

    Должность — пустая строка: колонка обязательна, а профиль без должности
    называется «Без должности».
    """
    return replace(
        parsed,
        profile=replace(
            parsed.profile,
            title="",
            education=None,
            work_format=[],
            grades=[],
            expected_salary=None,
            expected_salary_currency=None,
            expected_salary_period=None,
            about_me=None,
            resume_url=None,
        ),
        preferences=[],
        skills=[],
        experience=[],
        projects=[],
    )
