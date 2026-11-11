"""Удаление профиля со всем своим; общее остаётся.

Отдельно от `workspaces.py`: удаление зовёт писателей вакансий и анкеты, а
они сами ввозят тот модуль — номер активного профиля, — и ввоз оттуда замкнул
бы круг.
"""

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import TrashEvent, Workspace
from backend.repository.profile import get_profile_in
from backend.repository.profile_cv import wipe_profile
from backend.repository.vacancies_life import delete_vacancies_of_workspace


async def delete_workspace_rows(session: AsyncSession, workspace_id: int) -> str:
    """Удалить профиль со всем своим; ответ — путь копии фото: её удаляет зовущий.

    Вакансии уходят с детьми, у писем ссылка на них снимается — переписка
    общая и остаётся. Тумблеры, отметки чтения и сопроводительные письма снимает каскад строки профиля. Файл копии фото здесь не трогается:
    сделку держит зовущий, и откатись она — фото пропало бы у живого профиля.
    """
    await delete_vacancies_of_workspace(session, workspace_id)
    await session.execute(delete(TrashEvent).where(TrashEvent.workspace_id == workspace_id))
    profile = await get_profile_in(session, workspace_id)
    if profile is not None:
        await wipe_profile(session, profile.id)
    workspace = await session.get(Workspace, workspace_id)
    photo_path = workspace.photo_path
    await session.delete(workspace)
    await session.flush()
    return photo_path
