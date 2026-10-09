"""Погашенная задача кончилась к возврату: после остановки она ничего не допишет."""

import asyncio

from backend.task_stop import put_out


async def test_the_task_is_over_when_put_out_returns():
    tidied = []

    async def work():
        try:
            await asyncio.sleep(3600)
        finally:
            await asyncio.sleep(0)
            tidied.append("убрано")

    task = asyncio.create_task(work())
    await asyncio.sleep(0)

    await put_out(task)

    assert tidied == ["убрано"]
