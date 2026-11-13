"""Профили: создание тремя способами, смена и удаление активного.

Каждая операция — своя сессия и одна сделка; файлы трогаются после сделки:
откатись она, копия фото осталась бы у профиля, которого нет, или пропала бы у
живого.

Зовут сюда бот — в месте прогона (`bot/workspaces.py`) — и мост, пока бота нет:
тогда нет ни места прогона, ни кэшей.
"""

import logging
from typing import Literal

from sqlalchemy import func, select

from backend.bot.media import drop_stored_media, store_profile_photo, stored_media
from backend.models import Workspace
from backend.repository.cover_letters import copy_letters
from backend.repository.profile_copy import copy_english_link, personal_part, profile_as_parsed
from backend.repository.profile_cv import save_parsed_cv
from backend.repository.workspace_removal import delete_workspace_rows
from backend.repository.workspace_switches import copy_switches
from backend.repository.workspaces import active_workspace, add_workspace, make_active

logger = logging.getLogger(__name__)

CreateWay = Literal["empty", "personal", "copy"]
"""Способ создания: пустой профиль, только личные данные, копия активного."""


async def create_workspace(session_factory, way: CreateWay) -> int:
    """Завести профиль из активного этим способом и сделать его активным; ответ — его номер.

    Файлы резюме и сопроводительные письма переносит только копия: в личных
    данных их нет — письмо пишется под должность, а не под человека. Фото
    переносят копия и личные данные — своей копией в каталоге нового профиля.
    Её путь пишется второй сделкой, после файла: упади запись файла — профиль
    останется без фото, а не с путём на несуществующий файл.
    """
    async with session_factory() as session:
        async with session.begin():
            source = await active_workspace(session)
            source_id = source.id
            parsed = None if way == "empty" else await profile_as_parsed(session)
            cv_path = source.cv_path if way == "copy" else ""
            cv_en_path = source.cv_en_path if way == "copy" else ""
            photo = None if way == "empty" else stored_media(source.photo_path)
            made = await add_workspace(session, cv_path=cv_path, cv_en_path=cv_en_path)
            if parsed is not None:
                await save_parsed_cv(
                    session, parsed if way == "copy" else personal_part(parsed),
                    workspace_id=made, cv_path=cv_path,
                )
                if way == "copy":
                    await copy_english_link(session, source_id, made)
            if way == "copy":
                await copy_switches(session, source_id, made)
                await copy_letters(session, source_id, made)
            await make_active(session, made)
    if photo is not None:
        relative = store_profile_photo(photo.read_bytes(), photo.suffix, made)
        async with session_factory() as session:
            async with session.begin():
                (await session.get(Workspace, made)).photo_path = relative
    logger.info("workspace %d created (%s) from %d", made, way, source_id)
    return made


async def switch_workspace(session_factory, workspace_id: int) -> bool:
    """Сделать профиль активным; ложь — такого профиля нет."""
    async with session_factory() as session:
        async with session.begin():
            switched = await make_active(session, workspace_id)
    if switched:
        logger.info("workspace %d is active", workspace_id)
    return switched


async def delete_active_workspace(session_factory) -> Literal["deleted", "last"]:
    """Удалить активный профиль со всем своим; затем активен первый по номеру.

    Единственный профиль не удаляется: без активного приложение не живёт.
    """
    async with session_factory() as session:
        async with session.begin():
            if await session.scalar(select(func.count()).select_from(Workspace)) == 1:
                return "last"
            gone = (await active_workspace(session)).id
            photo_path = await delete_workspace_rows(session, gone)
            first = await session.scalar(select(func.min(Workspace.id)))
            await make_active(session, first)
    drop_stored_media(photo_path)
    logger.info("workspace %d deleted, %d is active", gone, first)
    return "deleted"
