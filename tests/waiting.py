"""Ожидание в тестах — с потолком: не наступи условие, тест падает, а не виснет."""

import asyncio


async def wait_until(condition) -> None:
    async def met():
        while not condition():
            await asyncio.sleep(0)

    await asyncio.wait_for(met(), 5)
