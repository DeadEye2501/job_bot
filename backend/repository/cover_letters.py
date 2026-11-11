"""Сопроводительные письма профиля: чтение, запись и перенос в новый профиль."""

from sqlalchemy import insert, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import CoverLetter
from backend.repository.workspaces import active_workspace_id

LETTER_FIELDS = ("ru", "ru_short", "en", "en_short")
"""Четыре письма: полное и короткое, по-русски и по-английски."""


async def get_letters(session: AsyncSession) -> CoverLetter | None:
    """Письма активного профиля; строки нет — писем не писали."""
    return await session.get(CoverLetter, await active_workspace_id(session))


async def save_letters(session: AsyncSession, **letters: str | None) -> None:
    """Заменить письма активного профиля присланными. Сделку держит зовущий."""
    workspace_id = await active_workspace_id(session)
    row = await session.get(CoverLetter, workspace_id)
    if row is None:
        session.add(CoverLetter(workspace_id=workspace_id, **letters))
    else:
        for name, text in letters.items():
            setattr(row, name, text)
    await session.flush()


async def copy_letters(session: AsyncSession, source_id: int, target_id: int) -> None:
    """Перенести письма из профиля в профиль. Сделку держит зовущий."""
    await session.execute(
        insert(CoverLetter).from_select(
            ["workspace_id", *LETTER_FIELDS],
            select(literal(target_id), *(getattr(CoverLetter, name) for name in LETTER_FIELDS))
            .where(CoverLetter.workspace_id == source_id),
        )
    )
