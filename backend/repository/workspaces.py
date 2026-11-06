"""Профили: какой активен, чей номер у вакансии, смена активного."""

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Vacancy, Workspace


async def active_workspace(session: AsyncSession) -> Workspace:
    """Строка активного профиля. Активен всегда ровно один: его кладёт миграция."""
    return (await session.scalars(select(Workspace).where(Workspace.is_active))).one()


async def active_workspace_id(session: AsyncSession) -> int:
    """Номер активного профиля."""
    return (await active_workspace(session)).id


async def owning_workspace_id(session: AsyncSession, vacancy_id: int | None) -> int:
    """Профиль вакансии; без вакансии или без её строки — активный.

    Без вакансии приходит письмо HR, которому мы не писали (`flows/dm.py`).
    Строки нет, когда вакансию удалили, пока письмо по ней ждало разбора:
    вердикт по ней отбросит `apply_classification`, а отклика на неё не будет.
    """
    owner = None if vacancy_id is None else await session.scalar(
        select(Vacancy.workspace_id).where(Vacancy.id == vacancy_id)
    )
    return owner if owner is not None else await active_workspace_id(session)


async def make_active(session: AsyncSession, workspace_id: int) -> bool:
    """Сделать профиль активным; ложь — такого профиля нет. Сделку держит зовущий.

    Двумя запросами, а не правкой атрибутов: правки ORM сбрасывает в порядке
    первичного ключа, и смена 2→1 поставила бы второй активный раньше, чем
    снят первый, — частичный уникальный индекс такого не пропустит.
    """
    if await session.get(Workspace, workspace_id) is None:
        return False
    await session.execute(update(Workspace).values(is_active=False))
    await session.execute(
        update(Workspace).where(Workspace.id == workspace_id).values(is_active=True)
    )
    return True
