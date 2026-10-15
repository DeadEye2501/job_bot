"""Языки, названные в анкете кандидата."""

import logging

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.language_choice import person_language, reply_language, search_languages
from backend.llm.candidate import candidate_languages
from backend.models import ProfileLanguage

logger = logging.getLogger(__name__)


async def list_profile_languages(
    session: AsyncSession,
) -> list[ProfileLanguage]:
    """Return all profile_language rows ordered by id (insertion order)."""
    rows = await session.scalars(
        select(ProfileLanguage).order_by(ProfileLanguage.id)
    )
    return list(rows)


async def read_user_language(session: AsyncSession) -> str:
    """Язык человека по его анкете — решение `domain/language_choice`."""
    return person_language(candidate_languages(await list_profile_languages(session)))


async def read_search_languages(session: AsyncSession) -> list[str]:
    """Языки поиска работы по анкете — решение `domain/language_choice`."""
    return search_languages(candidate_languages(await list_profile_languages(session)))


async def read_reply_language(session: AsyncSession, vacancy_language: str | None) -> str:
    """Язык отклика на вакансию с этим языком — решение `domain/language_choice`."""
    return reply_language(vacancy_language, await read_user_language(session))


async def replace_profile_languages(
    session: AsyncSession,
    profile_id: int,
    items: list[tuple[str, str]],
) -> None:
    """Wipe and re-insert profile_language rows for ``profile_id``.

    Caller must wrap in ``session.begin()``. The table is small (1-5 rows
    per profile), so a full replace is simpler than diff-and-update and
    keeps the (profile_id, language) uniqueness invariant trivially true.
    """
    await session.execute(
        delete(ProfileLanguage).where(
            ProfileLanguage.profile_id == profile_id
        )
    )
    await session.flush()
    for language, level in items:
        session.add(
            ProfileLanguage(
                profile_id=profile_id, language=language, level=level
            )
        )
    await session.flush()
    logger.debug("Profile languages replaced (count=%d)", len(items))
