"""Зов инструмента сессии настоящим клиентом MCP — так, как его зовёт агент."""

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


async def call_tool(url: str, name: str, arguments: dict) -> None:
    """Позвать инструмент по адресу сервера и дождаться ответа."""
    async with streamable_http_client(url) as (read, write, _):
        async with ClientSession(read, write) as client:
            await client.initialize()
            await client.call_tool(name, arguments)
