"""Места работы, названные в анкете кандидата."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.incoming import date_or_refusal, str_list, text_or_none
from backend.models import ProfileExperience, profile_experience_skills
from backend.repository.profile_records import RecordKind, replace_records, wipe_records


async def wipe_experience(session: AsyncSession) -> None:
    """Стереть места работы вместе со связками «место — навык»."""
    await wipe_records(session, EXPERIENCE)


async def list_experience(session: AsyncSession) -> list[ProfileExperience]:
    """All ProfileExperience rows newest-first, with skills relationship loaded."""
    return list(
        (
            await session.scalars(
                select(ProfileExperience)
                .options(selectinload(ProfileExperience.skills))
                .order_by(ProfileExperience.start_date.desc())
            )
        ).all()
    )


def _experience_fields(row: dict) -> dict:
    """Поля места работы из строки окна: компания, должность и дата начала
    обязательны, дата конца — нет: «по настоящее время» — обычный случай."""
    company = (row.get("company") or "").strip()
    if not company:
        raise ValueError("не заполнено название компании")
    role = (row.get("role") or "").strip()
    if not role:
        raise ValueError("не заполнена должность")
    start_date = date_or_refusal(row.get("start_date"), "начала")
    if start_date is None:
        raise ValueError("не заполнена дата начала")
    return {
        "company": company,
        "company_url": text_or_none(row.get("company_url")),
        "role": role,
        "start_date": start_date,
        "end_date": date_or_refusal(row.get("end_date"), "окончания"),
        "achievements": str_list(row.get("achievements")),
        "responsibilities": str_list(row.get("responsibilities")),
    }


EXPERIENCE = RecordKind(ProfileExperience, profile_experience_skills, _experience_fields)


async def save_experience(session: AsyncSession, rows: list[dict], profile_id: int) -> None:
    """Заменить места работы присланными; плохая строка — ``RowError`` до записи."""
    await replace_records(session, rows, profile_id, EXPERIENCE)
