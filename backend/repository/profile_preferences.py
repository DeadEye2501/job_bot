"""Строки предпочтений, названные в анкете кандидата."""

from sqlalchemy import ColumnElement, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import PreferenceKind, ProfilePreference
from backend.models.workspace import ACTIVE_WORKSPACE_ID
from backend.repository.profile import profile_id_of


async def list_profile_preferences_in(
    session: AsyncSession, workspace_id: int | ColumnElement[int]
) -> list[ProfilePreference]:
    """Строки предпочтений анкеты профиля в порядке заведения."""
    rows = await session.scalars(
        select(ProfilePreference)
        .where(ProfilePreference.profile_id == profile_id_of(workspace_id))
        .order_by(ProfilePreference.id)
    )
    return list(rows)


async def list_profile_preferences(session: AsyncSession) -> list[ProfilePreference]:
    """Строки предпочтений анкеты активного профиля в порядке заведения."""
    return await list_profile_preferences_in(session, ACTIVE_WORKSPACE_ID)


async def replace_profile_preferences(
    session: AsyncSession, profile_id: int, items: list[tuple[PreferenceKind, str]]
) -> None:
    """Стереть строки предпочтений профиля и записать присланные.

    Целиком, как языки: строк единицы, а порядок анкеты держит `id`.
    Сделку держит зовущий.
    """
    await session.execute(delete(ProfilePreference).where(ProfilePreference.profile_id == profile_id))
    session.add_all(ProfilePreference(profile_id=profile_id, kind=kind, text=text) for kind, text in items)
    await session.flush()
