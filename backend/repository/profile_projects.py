"""Проекты из анкеты кандидата."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.incoming import str_list, text_or_none
from backend.models import ProfileProject, profile_project_skills
from backend.repository.profile_records import RecordKind, replace_records, wipe_records


async def wipe_projects(session: AsyncSession) -> None:
    """Стереть проекты вместе со связками «проект — навык»."""
    await wipe_records(session, PROJECTS)


async def list_projects(session: AsyncSession) -> list[ProfileProject]:
    """Проекты в порядке записи, со стеком.

    Дат у проекта нет, и порядок — тот, в котором перечень записали: окно
    шлёт его в показанном порядке, разбор резюме — в порядке резюме.
    """
    return list(
        (
            await session.scalars(
                select(ProfileProject)
                .options(selectinload(ProfileProject.skills))
                .order_by(ProfileProject.id)
            )
        ).all()
    )


def _project_fields(row: dict) -> dict:
    """Поля проекта из строки окна; обязательно одно название."""
    name = (row.get("name") or "").strip()
    if not name:
        raise ValueError("не заполнено название проекта")
    return {
        "name": name,
        "url": text_or_none(row.get("url")),
        "about": str_list(row.get("about")),
    }


PROJECTS = RecordKind(ProfileProject, profile_project_skills, _project_fields)


async def save_projects(session: AsyncSession, rows: list[dict], profile_id: int) -> None:
    """Заменить проекты присланными; плохая строка — ``RowError`` до записи."""
    await replace_records(session, rows, profile_id, PROJECTS)
