"""Поля анкеты кандидата."""

import logging

from sqlalchemy import ColumnElement, ScalarSelect, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Profile
from backend.models.workspace import ACTIVE_WORKSPACE_ID
from backend.repository.workspaces import active_workspace_id

logger = logging.getLogger(__name__)


def profile_id_of(workspace_id: int | ColumnElement[int]) -> ScalarSelect:
    """Номер анкеты профиля подзапросом; годится и для `ACTIVE_WORKSPACE_ID`."""
    return select(Profile.id).where(Profile.workspace_id == workspace_id).scalar_subquery()


async def get_profile_in(
    session: AsyncSession, workspace_id: int | ColumnElement[int]
) -> Profile | None:
    """Анкета профиля, если она есть: до первой анкеты профиль живёт без неё."""
    return (await session.scalars(
        select(Profile).where(Profile.workspace_id == workspace_id)
    )).one_or_none()


async def get_profile(session: AsyncSession) -> Profile | None:
    """Анкета активного профиля, если она есть."""
    return await get_profile_in(session, ACTIVE_WORKSPACE_ID)


async def upsert_profile(session: AsyncSession, **fields) -> Profile:
    """Update the active workspace's Profile row basic fields, or create it.

    Caller must wrap in ``session.begin()``. Skills and experience are NOT
    touched here — those have their own write paths.
    """
    profile = await get_profile(session)
    if profile is None:
        profile = Profile(workspace_id=await active_workspace_id(session), **fields)
        session.add(profile)
    else:
        for key, value in fields.items():
            setattr(profile, key, value)
    await session.flush()
    logger.debug("Profile upserted (fields=%s)", list(fields.keys()))
    return profile
