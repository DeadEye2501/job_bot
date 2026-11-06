"""Языки, названные в анкете кандидата."""

import logging

from sqlalchemy import ColumnElement, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.language_choice import (
    candidate_languages,
    person_language,
    reply_language,
    search_languages,
)
from backend.models import ProfileLanguage, Vacancy
from backend.models.workspace import ACTIVE_WORKSPACE_ID
from backend.repository.profile import profile_id_of
from backend.repository.workspaces import owning_workspace_id

logger = logging.getLogger(__name__)


async def _languages_in(
    session: AsyncSession, workspace_id: int | ColumnElement[int]
) -> list[ProfileLanguage]:
    """Языки анкеты профиля в порядке заведения."""
    rows = await session.scalars(
        select(ProfileLanguage)
        .where(ProfileLanguage.profile_id == profile_id_of(workspace_id))
        .order_by(ProfileLanguage.id)
    )
    return list(rows)


async def list_profile_languages(
    session: AsyncSession,
) -> list[ProfileLanguage]:
    """Языки анкеты активного профиля в порядке заведения."""
    return await _languages_in(session, ACTIVE_WORKSPACE_ID)


async def read_user_language_in(
    session: AsyncSession, workspace_id: int | ColumnElement[int]
) -> str:
    """Язык человека по анкете профиля — решение `domain/language_choice`."""
    return person_language(candidate_languages(await _languages_in(session, workspace_id)))


async def read_user_language(session: AsyncSession) -> str:
    """Язык человека по анкете активного профиля."""
    return await read_user_language_in(session, ACTIVE_WORKSPACE_ID)


async def read_search_languages(session: AsyncSession) -> list[str]:
    """Языки поиска работы по анкете — решение `domain/language_choice`."""
    return search_languages(candidate_languages(await list_profile_languages(session)))


async def read_reply_language(session: AsyncSession, vacancy_id: int) -> str:
    """Язык отклика на вакансию — решение `domain/language_choice`.

    Человек — по анкете профиля вакансии. Вакансии нет — язык человека по
    анкете активного: отклика на неё не будет, и откуда пропажа, зовущий
    узнаёт сам, читая вакансию.
    """
    vacancy = await session.get(Vacancy, vacancy_id)
    person = await read_user_language_in(session, await owning_workspace_id(session, vacancy_id))
    return reply_language(vacancy.language if vacancy else None, person)


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
