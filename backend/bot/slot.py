"""Единственное место прогона: пока оно занято, второй цикл получает отказ.

Сосед `loop.py` решает, **когда** прогонять; здесь — **где** прогон живёт.
"""

import asyncio
import logging

from typing import Any, Callable, Literal

from backend.notify import fire

logger = logging.getLogger(__name__)

CycleOutcome = Literal["ok", "busy", "cancelled", "error"]
"""Чем кончилось действие, занимавшее место прогона.

Имя одно на всех, кто это место занимает, и на фасад бота, который их
пересказывает окну: переписанный значениями перечень разошёлся бы с этим
молча — новый исход добавили бы сюда, а фасад продолжал бы обещать старое.
Действия с исходами богаче добавляют к нему свои имена (`ChannelPollOutcome`,
`RerunOutcome`), а не выписывают перечень заново.
"""


def on_runner_loop(bot, action: Callable[[], Any]) -> None:
    """Сделать это на цикле бота, а не в том потоке, откуда позвали.

    Зовут отсюда из потока окна, а `asyncio.Event` и `Task` изнутри ходят по
    своим ожидающим и сами планируют `loop.call_soon` — из чужого потока это
    иногда роняет. Пока цикла нет (бот ещё не поднялся) или он уже закрыт,
    делаем прямо: ожидающих у события в этот миг нет, а задачи прогона нет и
    подавно.
    """
    loop = bot.loop
    if loop is not None and not loop.is_closed():
        loop.call_soon_threadsafe(action)
    else:
        action()


def cancel_current_poll(bot) -> None:
    """Cancel an in-flight poll cycle without stopping the whole bot."""
    task = bot.current_poll_task
    if task is None or task.done():
        return
    logger.info("Cancel current poll requested")
    on_runner_loop(bot, task.cancel)


async def _run_task(bot, work: Callable[[], Any], label: str):
    """Прогнать работу задачей; отдать исход и её ответ.

    Задача заводится нарочно, а не ожидается корутина: отмену из окна
    получает именно она, и по ней же читается занятость места. Отмена и
    сбой разводятся здесь: первое — решение человека, второе — беда, и
    зовущий говорит о них разными словами.

    Отмен две, и путать их нельзя. Отменили саму задачу — это отмена прогона,
    и она исход. Отменили нас — закрывается окно, и отмена идёт дальше
    наружу: приняв её за свою, цикл пошёл бы гасить соединения под живой
    задачей обхода, а та осталась бы читать канал и писать в закрытую базу.

    Различает их счётчик отмен нашей же задачи: отменённая задача прогона
    роняет `CancelledError` и в нас, но просьб отмениться у нас при этом нет
    ни одной.
    """
    try:
        task = asyncio.create_task(work())
        bot.current_poll_task = task
        try:
            return "ok", await task
        except asyncio.CancelledError:
            ours = asyncio.current_task()
            if ours is not None and ours.cancelling() > 0:
                raise
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
    if bot.current_poll_task is not None:
        logger.info("%s: another cycle is already running, skipping", label)
        return "busy", None
    fire(bot.on_cycle_start, "on_cycle_start")
    if progress is not None:
        fire(bot.on_progress, "on_progress", *progress)
    try:
        outcome, result = await _run_task(bot, work, label)
    finally:
        bot.current_poll_task = None
        fire(bot.on_cycle_end, "on_cycle_end")
    return outcome, result
