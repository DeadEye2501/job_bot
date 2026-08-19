"""Поля анкеты кандидата."""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Profile

logger = logging.getLogger(__name__)


async def get_profile(session: AsyncSession) -> Profile | None:
    """Return the single Profile row, if any."""
    return (await session.scalars(select(Profile).limit(1))).first()


async def upsert_profile(session: AsyncSession, **fields) -> Profile:
    """Update the single Profile row's basic fields, or create it.

    Caller must wrap in ``session.begin()``. Skills and experience are NOT
    touched here — those have their own write paths.
    """
    profile = await get_profile(session)
    if profile is None:
        profile = Profile(**fields)
        session.add(profile)
    else:
        for key, value in fields.items():
            setattr(profile, key, value)
    await session.flush()
    logger.debug("Profile upserted (fields=%s)", list(fields.keys()))
    return profile
