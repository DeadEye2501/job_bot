"""Смена, создание и удаление профиля при поднятом боте — в месте прогона.

Место прогона — замок: пока идёт обход или действие окна, профиль под ним не
меняется. Слепки конвейера и настройки перечитываются там же, до освобождения
места: цикл, занявший его следом, видит уже новый профиль.
"""

from collections.abc import Awaitable, Callable
from typing import Literal

from backend.bot import slot
from backend.flows import workspaces as flows


async def _then_forget(bot, flow: Callable[[], Awaitable], label: str):
    """Ответ работы с профилями в месте прогона — или отказ самого места.

    Слепки и настройки перечитываются после любого конца работы, и сбоя тоже:
    сбой бывает и после записанной смены (упала запись копии фото, нажат
    «Стоп»), и тогда в памяти остался бы прежний профиль. Лишний сброс стоит
    одного подъёма.
    """
    async def work():
        try:
            return await flow()
        finally:
            bot.ingestion.forget_caches()
            await bot.rs.reload()

    return await slot.answer_in_slot(bot, work, label)


async def create(bot, way: flows.CreateWay) -> int | slot.CycleOutcome:
    """Завести профиль этим способом и сделать его активным; ответ — его номер."""
    return await _then_forget(
        bot, lambda: flows.create_workspace(bot.session_factory, way), "create workspace"
    )


async def switch(bot, workspace_id: int) -> bool | slot.CycleOutcome:
    """Сделать профиль активным; ложь — такого профиля нет."""
    return await _then_forget(
        bot, lambda: flows.switch_workspace(bot.session_factory, workspace_id), "switch workspace"
    )


async def delete(bot) -> Literal["deleted", "last"] | slot.CycleOutcome:
    """Удалить активный профиль: `deleted` или `last` — он единственный."""
    return await _then_forget(
        bot, lambda: flows.delete_active_workspace(bot.session_factory), "delete workspace"
    )
