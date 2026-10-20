"""Инструменты сессии доступны по своему адресу и только по нему."""

import asyncio
import time

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from adapters.agent_mcp import serve_tools
from tests.mcp_call import call_tool


async def _echo(text: str) -> str:
    """Повторить текст."""
    return f"эхо: {text}"


async def test_a_tool_is_called_through_the_session_address():
    server = await serve_tools([_echo])
    try:
        async with streamable_http_client(server.url) as (read, write, _):
            async with ClientSession(read, write) as client:
                await client.initialize()
                names = [t.name for t in (await client.list_tools()).tools]
                result = await client.call_tool("_echo", {"text": "привет"})
    finally:
        await server.close()

    assert names == ["_echo"]
    assert result.content[0].text == "эхо: привет"


async def test_an_address_without_the_token_leads_nowhere():
    server = await serve_tools([_echo])
    try:
        bare = server.url.rsplit("/", 2)[0] + "/mcp"
        async with httpx.AsyncClient() as client:
            answer = await client.post(bare, json={})
    finally:
        await server.close()

    assert answer.status_code == 404


async def test_a_closed_server_leaves_no_task_behind():
    """Закрытый сервер гасит своё приложение целиком: оставленная задача
    висела бы до закрытия окна, а там гасилась бы с ошибкой в журнале."""
    before = asyncio.all_tasks()
    server = await serve_tools([_echo])

    await server.close()
    await asyncio.sleep(0)

    assert asyncio.all_tasks() - before == set()


async def test_a_hanging_call_does_not_hold_the_close():
    """Вызов, ждущий человека, не держит остановку: сессия к закрытию сервера
    уже кончилась, и ждать её вызов незачем — окно ждёт остановки бота
    считанные секунды."""
    started = asyncio.Event()

    async def _wait() -> str:
        """Ждать вечно."""
        started.set()
        await asyncio.Event().wait()
        return ""

    server = await serve_tools([_wait])

    caller = asyncio.create_task(call_tool(server.url, "_wait", {}))
    await asyncio.wait_for(started.wait(), 10)
    began = time.monotonic()

    await asyncio.wait_for(server.close(), 10)

    assert time.monotonic() - began < 2
    caller.cancel()
    await asyncio.gather(caller, return_exceptions=True)
