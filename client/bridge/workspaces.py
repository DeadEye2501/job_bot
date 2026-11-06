"""Профили: перечень с именами, создание, смена и удаление активного.

При поднятом боте работа идёт через него — в месте прогона, которое и есть
замок, — и конвейер забывает слепки прежнего профиля. Без бота мост зовёт
поток сам: ни места прогона, ни кэшей тогда нет.
"""

from __future__ import annotations

from typing import get_args

from backend.flows.workspaces import (
    CreateWay,
    create_workspace,
    delete_active_workspace,
    switch_workspace,
)
from backend.repository.workspaces import list_workspaces
from client.bridge.answer import BAD_PAYLOAD, Denied, bad_fields, reply
from client.bridge.events import LIST_CHANGED
from client.bridge.hub import Hub
from client.bridge.refusals import NO_WORKSPACE, WORKSPACE_REFUSALS

NO_TITLE = "Без должности"
"""Имя профиля, у анкеты которого должности нет: отдельного имени у профиля нет."""


class Workspaces:
    """Профили: что окно о них знает и что с ними делает."""

    def __init__(self, hub: Hub) -> None:
        self._hub = hub

    def list(self) -> dict:
        """Профили по номеру с именами.

        Замков здесь нет: обход окно знает само и живым, а снимок замка
        устарел бы к нажатию; единственный профиль видно по числу строк.
        """

        async def run() -> dict:
            async with self._hub.session_factory() as session:
                rows = await list_workspaces(session)
            return {
                "items": [
                    {"id": r.id, "name": NO_TITLE if r.title is None else r.title,
                     "active": r.is_active}
                    for r in rows
                ],
            }

        return reply(self._hub.runner, run())

    def create(self, way) -> dict:
        """Завести профиль способом, выбранным в окне, и сделать его активным."""
        if way not in get_args(CreateWay):
            return bad_fields("workspaces.create", ValueError(f"unknown way {way!r}"))
        return self._changed(
            lambda bot: bot.ui_create_workspace(way),
            lambda: create_workspace(self._hub.session_factory, way),
        )

    def switch(self, workspace_id) -> dict:
        """Сделать профиль активным."""
        try:
            workspace_id = int(workspace_id)
        except BAD_PAYLOAD as e:
            return bad_fields("workspaces.switch", e)
        return self._changed(
            lambda bot: bot.ui_switch_workspace(workspace_id),
            lambda: switch_workspace(self._hub.session_factory, workspace_id),
        )

    def remove(self) -> dict:
        """Удалить активный профиль; активным станет первый по номеру."""
        return self._changed(
            lambda bot: bot.ui_delete_workspace(),
            lambda: delete_active_workspace(self._hub.session_factory),
        )

    def _changed(self, on_bot, alone) -> dict:
        """Работа с профилями через бота или без него; окно перечитывает своё после любого конца.

        После любого, а не после удачи: сбой бывает и после записанной смены
        (упала запись копии фото), и окно показывало бы прежний профиль. Без
        бота настройки перечитываются здесь — пути резюме и фото в них
        активного профиля; бот перечитывает их сам, в месте прогона.
        """
        hub = self._hub
        bot = hub.bot

        async def alone_then_reload():
            try:
                return await alone()
            finally:
                await hub.rs.reload()

        async def run() -> dict:
            try:
                said = await (on_bot(bot) if bot is not None else alone_then_reload())
            finally:
                hub.events.add(LIST_CHANGED)
                hub.events.add("contacts_lists_changed")
            if said is False:
                raise Denied(NO_WORKSPACE)
            if isinstance(said, str) and said in WORKSPACE_REFUSALS:
                raise Denied(WORKSPACE_REFUSALS[said])
            return {}

        return reply(hub.runner, run())
