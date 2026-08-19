"""Места работы, названные в анкете кандидата."""

import logging
from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.skill_names import skill_key
from backend.domain.spellings import dedupe_first_wins
from backend.incoming import str_list, text_or_none
from backend.models import (
    ProfileExperience,
    ProfileSkill,
    profile_experience_skills,
)
from backend.repository.profile_skills import index_skill_keys, list_skills

logger = logging.getLogger(__name__)


async def wipe_experience(session: AsyncSession) -> None:
    """Стереть места работы вместе со связками «место — навык».

    Порядок несущий: проверка внешних ключей у этого движка включена, и
    сотри места первыми — база отказала бы, потому что на них ещё смотрят
    связки. Стирают опыт две дороги — разбор резюме и запись из окна, — и
    порядок у них один.
    """
    await session.execute(delete(profile_experience_skills))
    await session.execute(delete(ProfileExperience))


def _skills_by_key(rows: list[ProfileSkill]) -> dict[str, ProfileSkill]:
    """Навыки анкеты по ключу их названия; прозвища сюда не идут.

    Прозвища знает разбор резюме, потому что стек места работы приходит от
    модели любым написанием. Окно же присылает выбранное из списка, то есть
    само название, и лишний ключ там только множил бы столкновения.
    """
    lookup: dict[str, ProfileSkill] = {}
    for row in rows:
        index_skill_keys(lookup, (row.name,), row, "save_experience")
    return lookup


async def list_experience(session: AsyncSession) -> list[ProfileExperience]:
    """All ProfileExperience rows newest-first, with skills relationship loaded."""
    from sqlalchemy.orm import selectinload

    return list(
        (
            await session.scalars(
                select(ProfileExperience)
                .options(selectinload(ProfileExperience.skills))
                .order_by(ProfileExperience.start_date.desc())
            )
        ).all()
    )


class SaveExperienceError(ValueError):
    """Raised on validation failure during save_experience.

    Attribute ``index`` is the 1-based row number that failed; ``problem``
    describes what's wrong in human-readable Russian for the UI.
    """

    def __init__(self, index: int, problem: str) -> None:
        self.index = index
        self.problem = problem
        super().__init__(f"Запись #{index}: {problem}")


def _checked_experience_rows(
    rows: list[dict],
) -> list[tuple[dict, date, date | None]]:
    """Проверить все строки мест работы и разобрать их даты.

    Проверка идёт до первой записи в базу: сорвись она посередине, человек
    потерял бы уже введённое. Номер строки едет в отказ, чтобы окно показало
    беду там, где она есть.
    """
    checked: list[tuple[dict, date, date | None]] = []
    for i, row in enumerate(rows, start=1):
        if not (row.get("company") or "").strip():
            raise SaveExperienceError(i, "не заполнено название компании")
        if not (row.get("role") or "").strip():
            raise SaveExperienceError(i, "не заполнена должность")
        start_iso = (row.get("start_date") or "").strip()
        if not start_iso:
            raise SaveExperienceError(i, "не заполнена дата начала")
        try:
            start_date = date.fromisoformat(start_iso)
        except ValueError:
            raise SaveExperienceError(i, f"неверная дата начала: {start_iso!r}")
        end_iso = (row.get("end_date") or "").strip()
        end_date: date | None = None
        if end_iso:
            try:
                end_date = date.fromisoformat(end_iso)
            except ValueError:
                raise SaveExperienceError(
                    i, f"неверная дата окончания: {end_iso!r}"
                )
        checked.append((row, start_date, end_date))
    return checked


def _add_experience_rows(
    session: AsyncSession, checked: list, profile_id: int, skills_by_name: dict
) -> None:
    """Записать места работы из окна, связав названные навыки с анкетой.

    Незнакомое название навыка отбрасывается молча: окно предлагает выбирать
    из заведённых, и своё сюда попадает разве что из устаревшей вкладки.
    """
    for row, start_date, end_date in checked:
        exp = ProfileExperience(
            profile_id=profile_id,
            company=row["company"].strip(),
            company_url=text_or_none(row.get("company_url")),
            role=row["role"].strip(),
            start_date=start_date,
            end_date=end_date,
            achievements=str_list(row.get("achievements")),
            responsibilities=str_list(row.get("responsibilities")),
        )
        # Повторы отсеиваются тем же ключом, каким навык и ищется: два его
        # написания («Node.js» и «Node JS») ведут к одной строке, и вторая
        # связь падает на первичном ключе, унося всю правку вкладки.
        for sname in dedupe_first_wins(
            [str(name) for name in row.get("skill_names") or []], skill_key
        ):
            s = skills_by_name.get(skill_key(sname))
            if s is not None:
                exp.skills.append(s)
        session.add(exp)


async def save_experience(
    session: AsyncSession,
    rows: list[dict],
    profile_id: int,
) -> None:
    """Replace all ProfileExperience rows + their skill links.

    Validates eagerly: on the first invalid row the call raises
    ``SaveExperienceError`` BEFORE any DB writes, so the caller can show a
    targeted error and the user doesn't lose data they typed. Skills are
    matched to existing ProfileSkill rows by name; unknown names are
    dropped silently (UI's skill picker only offers existing skills).

    Caller wraps in ``session.begin()``.
    """
    skills_by_name = _skills_by_key(await list_skills(session))
    parsed_rows = _checked_experience_rows(rows)
    await wipe_experience(session)
    await session.flush()
    _add_experience_rows(session, parsed_rows, profile_id, skills_by_name)
    await session.flush()
    logger.debug("Saved experiences: %d rows", len(parsed_rows))
