"""Единственное место прогона: пока оно занято, второй цикл получает отказ.

Сосед `loop.py` решает, **когда** прогонять; здесь — **где** прогон живёт.
"""

import asyncio
import logging

from typing import Any, Callable, Literal

from backend.notify import fire

logger = logging.getLogger(__name__)

CycleOutcome = Literal["ok", "busy", "cancelled", "error"]


async def run_in_slot(
    bot,
    work: Callable[[], Any],
    label: str,
    progress: tuple | None = None,
) -> tuple[CycleOutcome, Any]:
    """Прогнать работу в единственном месте прогона.

    Место одно: два цикла разом подрались бы за кэш векторов и за курсор
    канала. Занятое место — отказ, а не ошибка: окно говорит о нём
    подсказкой, и зовущий переводит исход в свои слова сам.

    Отдаёт исход и то, что вернула работа. Место освобождается всегда —
    и после успеха, и после отмены, и после сбоя, — иначе кнопка
    «прогнать» замирает навсегда: занятость читается по тому же полю.

    ``work`` принимается вызываемым, а не готовой корутиной: при занятом
    месте её никто не станет ждать, и она осталась бы висеть
    неисполненной.
    """
    if bot._current_poll_task is not None:
        logger.info("%s: another cycle is already running, skipping", label)
        return "busy", None
    fire(bot.on_cycle_start, "on_cycle_start")
    if progress is not None:
        fire(bot.on_progress, "on_progress", *progress)
    outcome: CycleOutcome = "ok"
    result: Any = None
    try:
        bot._current_poll_task = asyncio.create_task(work())
        try:
            result = await bot._current_poll_task
        except asyncio.CancelledError:
            logger.info("%s cancelled by user", label)
            outcome = "cancelled"
    except Exception:
        logger.exception("%s failed", label)
        outcome = "error"
    finally:
        bot._current_poll_task = None
        fire(bot.on_cycle_end, "on_cycle_end")
    return outcome, result
