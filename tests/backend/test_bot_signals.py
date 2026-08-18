"""Следствия сигналов, приходящих боту из чужого потока.

Кнопки окна живут в потоке Qt, а события и задачи бота — на его собственном
цикле. Трогать их напрямую из чужого потока нельзя, поэтому каждый сигнал
идёт через `call_soon_threadsafe`. Пока цикл не захвачен или уже закрыт,
планировать некуда — тогда сигнал срабатывает на месте, иначе кнопка «стоп»
до запуска и после остановки не делала бы ничего.
"""

import asyncio

import pytest


@pytest.fixture
def closed_loop():
    """Закрытый цикл событий: так выглядит бот после остановки."""
    loop = asyncio.new_event_loop()
    loop.close()
    return loop


async def test_a_bot_is_not_ready_until_it_captures_its_loop(make_bot):
    """До захвата цикла бот не готов.

    Окно смотрит на этот признак перед каждым обращением к боту: до
    захвата клиент Telegram ещё не подключён, и вызов попал бы в
    полусобранное состояние.
    """
    bot = await make_bot()

    assert bot.is_ready is False

    bot.loop = asyncio.get_running_loop()

    assert bot.is_ready is True


async def test_a_wake_signal_reaches_the_loop(make_bot):
    """Побудка доходит до цикла, а не выставляется мимо него."""
    bot = await make_bot()
    bot.loop = asyncio.get_running_loop()

    bot.kick()
    assert not bot.wake_event.is_set()

    await asyncio.sleep(0)
    assert bot.wake_event.is_set()


@pytest.mark.parametrize("captured", [False, True], ids=["цикла нет", "цикл закрыт"])
async def test_a_wake_signal_without_a_live_loop_fires_on_the_spot(
    make_bot, closed_loop, captured
):
    """Без живого цикла побудка срабатывает на месте.

    Планировать некуда: до запуска цикла ещё нет, после остановки он уже
    закрыт. Оба раза выставить событие можно прямо здесь — планирование
    на закрытый цикл упало бы.
    """
    bot = await make_bot()
    bot.loop = closed_loop if captured else None

    bot.kick()

    assert bot.wake_event.is_set()


async def test_a_stop_signal_also_wakes_the_loop(make_bot):
    """Остановка ещё и будит цикл, а не только просит остановиться.

    Между прогонами бот спит до получаса. Без побудки просьба
    остановиться дошла бы только к концу сна.
    """
    bot = await make_bot()
    bot.loop = asyncio.get_running_loop()

    bot.request_stop()
    await asyncio.sleep(0)

    assert bot.stop_event.is_set()
    assert bot.wake_event.is_set()


@pytest.mark.parametrize("captured", [False, True], ids=["цикла нет", "цикл закрыт"])
async def test_a_stop_signal_without_a_live_loop_fires_on_the_spot(
    make_bot, closed_loop, captured
):
    """Без живого цикла остановка срабатывает на месте."""
    bot = await make_bot()
    bot.loop = closed_loop if captured else None

    bot.request_stop()

    assert bot.stop_event.is_set()
    assert bot.wake_event.is_set()


async def test_cancelling_a_poll_reaches_the_running_task(make_bot):
    """Отмена прогона доходит до запущенной задачи."""
    bot = await make_bot()
    bot.loop = asyncio.get_running_loop()
    task = asyncio.create_task(asyncio.sleep(30))
    bot.current_poll_task = task

    bot.cancel_current_poll()
    assert not task.cancelled()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert task.cancelled()


async def test_cancelling_without_a_live_loop_reaches_the_task_too(
    make_bot, closed_loop
):
    """Без живого цикла отмена доходит до задачи прямо здесь."""
    bot = await make_bot()
    bot.loop = closed_loop
    task = asyncio.create_task(asyncio.sleep(30))
    bot.current_poll_task = task

    bot.cancel_current_poll()

    with pytest.raises(asyncio.CancelledError):
        await task


async def test_cancelling_a_finished_poll_does_nothing(make_bot):
    """Отмена завершённого прогона ничего не делает.

    Кнопка «стоп» остаётся нажимаемой и после того, как прогон кончился
    сам; повторная отмена не должна ни падать, ни трогать чужое.
    """
    bot = await make_bot()
    bot.loop = asyncio.get_running_loop()
    task = asyncio.create_task(asyncio.sleep(0))
    await task
    bot.current_poll_task = task

    bot.cancel_current_poll()

    assert not task.cancelled()


async def test_cancelling_when_nothing_runs_does_nothing(make_bot):
    """Отмена при отсутствии прогона ничего не делает и не падает."""
    bot = await make_bot()
    bot.loop = asyncio.get_running_loop()

    bot.cancel_current_poll()

    assert bot.current_poll_task is None
