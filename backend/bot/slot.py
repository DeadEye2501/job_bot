"""Единственное место прогона: пока оно занято, второй цикл получает отказ.

Сосед `loop.py` решает, **когда** прогонять; здесь — **где** прогон живёт.
"""

import asyncio
import logging

from typing import Any, Callable, Literal

from backend.notify import fire

logger = logging.getLogger(__name__)

CycleOutcome = Literal["ok", "busy", "cancelled", "error"]


def cancel_current_poll(bot) -> None:
    """Cancel an in-flight poll cycle without stopping the whole bot.

    Thread-safe: см. ``kick``. Task.cancel() из чужого треда мутирует
    внутреннее состояние Task'а и пытается loop.call_soon — обязан
    идти через call_soon_threadsafe.
    """
    task = bot._current_poll_task
    if task is None or task.done():
        return
    logger.info("Cancel current poll requested")
    loop = bot._loop
    if loop is not None and not loop.is_closed():
        loop.call_soon_threadsafe(task.cancel)
    else:
        task.cancel()


async def _run_task(bot, work: Callable[[], Any], label: str):
    """Прогнать работу задачей; отдать исход и её ответ.

    Задача заводится нарочно, а не ожидается корутина: отмену из окна
    получает именно она, и по ней же читается занятость места. Отмена и
    сбой разводятся здесь: первое — решение человека, второе — беда, и
    зовущий говорит о них разными словами.
    """
    try:
        bot._current_poll_task = asyncio.create_task(work())
        try:
            return "ok", await bot._current_poll_task
        except asyncio.CancelledError:
            logger.info("%s cancelled by user", label)
            return "cancelled", None
    except Exception:
        logger.exception("%s failed", label)
        return "error", None


async def run_in_slot(
    bot,
    work: Callable[[], Any],
    label: str,
    progress: tuple[str, str, int, int] | None = None,
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
    try:
        outcome, result = await _run_task(bot, work, label)
    finally:
        bot._current_poll_task = None
        fire(bot.on_cycle_end, "on_cycle_end")
    return outcome, result
