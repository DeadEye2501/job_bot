"""Место прогона, занятое отдельной задачей: цикл бота не ждёт её, место держится до конца."""

import asyncio
import logging

from backend.bot import slot
from tests.backend.fixtures.bot import slot_freed


async def test_a_launched_work_holds_the_slot_until_it_ends(make_bot):
    bot = await make_bot()
    release = asyncio.Event()

    async def work():
        await release.wait()

    assert slot.launch_in_slot(bot, work, "aggregator round") is True
    await asyncio.sleep(0)

    assert slot.launch_in_slot(bot, work, "aggregator round") is False
    assert (await slot.run_in_slot(bot, work, "poll cycle"))[0] == "busy"
    release.set()
    await slot_freed(bot)
    assert bot.current_poll_task is None


async def test_a_failing_work_is_logged_and_frees_the_slot(make_bot, caplog):
    bot = await make_bot()
    ends = []
    bot.on_cycle_end = lambda: ends.append(True)

    async def work():
        raise RuntimeError("сломалось")

    with caplog.at_level(logging.ERROR, logger="backend.bot.slot"):
        slot.launch_in_slot(bot, work, "aggregator round")
        await slot_freed(bot)

    assert "aggregator round failed" in caplog.text
    assert ends == [True]


async def test_a_stop_is_a_cancellation_not_a_failure(make_bot, caplog):
    bot = await make_bot()

    async def work():
        await asyncio.sleep(3600)

    with caplog.at_level(logging.INFO, logger="backend.bot.slot"):
        slot.launch_in_slot(bot, work, "aggregator round")
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        slot.cancel_current_poll(bot)
        await slot_freed(bot)

    assert "aggregator round cancelled by user" in caplog.text
    assert "failed" not in caplog.text


async def test_settling_the_slot_puts_the_work_out_and_waits_for_it(make_bot):
    """Остановка бота ждёт обход: клиенты не закрываются под живой работой."""
    bot = await make_bot()
    tidied = []

    async def work():
        try:
            await asyncio.sleep(3600)
        finally:
            await asyncio.sleep(0)
            tidied.append(True)

    slot.launch_in_slot(bot, work, "aggregator round")
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    await slot.settle_slot(bot, timeout=5)

    assert tidied == [True] and bot.current_poll_task is None


async def test_settling_a_work_put_out_before_its_first_step_does_not_raise(make_bot):
    """Остановка идёт дальше к закрытию клиентов, как бы ни кончилась работа."""
    bot = await make_bot()

    async def work():
        await asyncio.sleep(3600)

    slot.launch_in_slot(bot, work, "aggregator round")
    bot.current_poll_task.cancel()

    await slot.settle_slot(bot, timeout=5)

    await slot_freed(bot)
    assert bot.current_poll_task is None
