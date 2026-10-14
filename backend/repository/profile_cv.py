"""Запись анкеты, разобранной моделью из резюме."""

import logging
from dataclasses import asdict

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from backend.repository.app_settings import CV_PATH_KEY, put_app_setting
from backend.models import (
    Profile,
    ProfileExperience,
    ProfileLanguage,
    ProfileProject,
    ProfileSkill,
)
from backend.payloads import ParsedCv
from backend.repository.profile import get_profile
from backend.repository.profile_experience import wipe_experience
from backend.repository.profile_languages import replace_profile_languages
from backend.repository.profile_projects import wipe_projects
from backend.repository.profile_records import link_stack
from backend.repository.profile_skills import index_skill_keys

logger = logging.getLogger(__name__)


async def _wipe_profile(session: AsyncSession) -> None:
    """Стереть анкету целиком — разбор резюме пишет её заново, а не дописывает.

    Частичное слияние оставляло бы в анкете навыки и языки из прошлого
    резюме, и человек об этом не узнал бы.
    """
    await wipe_experience(session)
    await wipe_projects(session)
    await session.execute(delete(ProfileSkill))
    await session.execute(delete(ProfileLanguage))
    await session.execute(delete(Profile))
    await session.flush()


async def _add_parsed_skills(
    session: AsyncSession, profile_id: int, skills
) -> dict[str, ProfileSkill]:
    """Записать навыки из резюме и вернуть их по ключам названий и прозвищ.

    Прозвища идут в ключи затем, что стек места работы приходит от модели
    любым написанием: по ним места и связываются с навыками.
    """
    lookup: dict[str, ProfileSkill] = {}
    for s in skills:
        row = ProfileSkill(
            profile_id=profile_id,
            category=s.category,
            name=s.name,
            level=s.level,
            aliases=list(s.aliases),
        )
        session.add(row)
        index_skill_keys(lookup, (s.name, *s.aliases), row, "save_parsed_cv")
    await session.flush()
    return lookup


def _parsed_records(model, records, profile_id: int, skill_lookup: dict[str, ProfileSkill]) -> list:
    """Строки мест работы или проектов из резюме, со стеком, связанным с навыками анкеты.

    Поля разобранной записи без стека — ровно колонки её модели. Технология,
    которой в анкете не нашлось, пропадает из связок с жалобой в журнал: молча
    потерянная связь выглядела бы как отсутствие опыта.
    """
    rows = []
    for record in records:
        fields = asdict(record)
        stack = fields.pop("stack")
        row = model(profile_id=profile_id, **fields)
        for tech in link_stack(row, stack, skill_lookup):
            # Первое поле разобранной записи — её название: компания или проект.
            logger.warning(
                "save_parsed_cv: %s %r stack item %r not matched to any ProfileSkill",
                model.__tablename__, next(iter(fields.values())), tech,
            )
        rows.append(row)
    return rows


_SALARY = ("expected_salary", "expected_salary_currency", "expected_salary_period")

_PERSON = (
    "first_name_latin", "last_name_latin", "gender", "patronymic", "patronymic_latin",
    "birth_date", "citizenship", "about_me", "resume_url",
)

_KEPT_ACROSS_RESUMES = _SALARY + _PERSON
"""Ответы для форм, которых в резюме может не быть. Повторный разбор их не
стирает: человек вводит их руками, а файл приносит редко."""


async def _answers_to_keep(session: AsyncSession) -> dict:
    old = await get_profile(session)
    if old is None:
        return {}
    return {name: getattr(old, name) for name in _KEPT_ACROSS_RESUMES}


def _answers(p, kept: dict) -> dict:
    """Ответы для форм: из файла, а чего файл не дал — прежние.

    Зарплата переносится связкой: новая сумма со старой валютой или периодом
    была бы чужой зарплатой.
    """
    fresh = p.expected_salary is not None
    answers = {name: getattr(p, name) if fresh else kept.get(name) for name in _SALARY}
    for name in _PERSON:
        answers[name] = getattr(p, name) if getattr(p, name) is not None else kept.get(name)
    return answers


def _new_profile(p, kept: dict) -> Profile:
    """Строка анкеты из разобранного резюме.

    Списки копируются, а не берутся ссылкой: разобранное резюме живёт своей
    жизнью, и правка анкеты в окне не должна доставать до него.
    """
    return Profile(
        first_name=p.first_name,
        last_name=p.last_name,
        title=p.title,
        email=p.email,
        phone=p.phone,
        location=p.location,
        telegram_username=p.telegram_username,
        github_url=p.github_url,
        education=p.education,
        work_format=list(p.work_format),
        grades=list(p.grades),
        free_preferences=p.free_preferences,
        **_answers(p, kept),
    )


async def save_parsed_cv(
    session: AsyncSession, parsed: ParsedCv, *, cv_path: str | None = None
) -> None:
    """Заменить анкету — с навыками, местами работы и проектами — разобранной.

    Путь к резюме пишется той же сделкой: сбой между двумя записями оставил бы
    разобранную анкету без записанного источника. Ответы для форм переносятся
    в новую строку, если файл их не дал. Сделку держит зовущий.
    """
    kept = await _answers_to_keep(session)
    await _wipe_profile(session)

    profile = _new_profile(parsed.profile, kept)
    session.add(profile)
    await session.flush()

    # Стирание внутри писателя здесь холостое — таблица снесена целиком выше.
    # Так и оставлено: свой цикл ради экономии одного запроса на разбор резюме
    # означал бы второе место, знающее устройство строки языка.
    await replace_profile_languages(
        session,
        profile.id,
        [(lang.language, lang.level) for lang in parsed.languages],
    )
    skill_lookup = await _add_parsed_skills(session, profile.id, parsed.skills)
    session.add_all([
        *_parsed_records(ProfileExperience, parsed.experience, profile.id, skill_lookup),
        *_parsed_records(ProfileProject, parsed.projects, profile.id, skill_lookup),
    ])
    await session.flush()
    if cv_path is not None:
        await put_app_setting(session, CV_PATH_KEY, cv_path)
        await session.flush()

    logger.info(
        "Profile replaced: languages=%d skills=%d experiences=%d projects=%d cv_path=%s",
        len(parsed.languages), len(parsed.skills), len(parsed.experience),
        len(parsed.projects), cv_path,
    )
