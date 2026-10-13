"""MCP-сервер инструментов одной сессии агента: HTTP на 127.0.0.1, токен в адресе."""

import asyncio
import logging
import secrets
import socket
from collections.abc import Callable
from dataclasses import dataclass

import uvicorn
from mcp.server.fastmcp import FastMCP

SERVER_NAME = "jobbot"
_START_SEC = 10
_CLOSE_SEC = 5
# Ждать закрытия дольше мягкой остановки: после неё сервер ещё гасит приложение.
_CLOSE_WAIT_SEC = _CLOSE_SEC * 2
logger = logging.getLogger(__name__)


@dataclass
class ToolServer:
    url: str
    _server: uvicorn.Server
    _task: asyncio.Task

    async def close(self) -> None:
        """Закрыть, не дожидаясь висящих вызовов: ждущий человека вызов иначе
        держал бы остановку до часа.

        Висящие вызовы гасит сам сервер по сроку мягкой остановки (`serve_tools`), а
        не принудительный выход: тот пропускает остановку приложения, и его
        задача висела бы до закрытия окна.
        """
        if self._task.done():
            return
        self._server.should_exit = True
        try:
            await asyncio.wait_for(self._task, _CLOSE_WAIT_SEC)
        except TimeoutError:
            logger.warning("MCP-сервер не закрылся за %s с, погашен", _CLOSE_WAIT_SEC)
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)


def tool_host(tools: list[Callable], **settings) -> FastMCP:
    """FastMCP с инструментами сессии: по их подписям он строит схему, которую
    видит агент, и проверяет по ней доводы каждого вызова."""
    mcp = FastMCP(SERVER_NAME, **settings)
    for tool in tools:
        mcp.add_tool(tool, name=tool.__name__, description=tool.__doc__ or "")
    return mcp


async def serve_tools(tools: list[Callable]) -> ToolServer:
    """Поднять сервер с инструментами сессии на свободном порту.

    Сервер на каждую сессию свой: инструменты замкнуты на её задачу, и
    токен в адресе не даёт чужому процессу на машине позвать их по
    угаданному порту.
    """
    token = secrets.token_urlsafe(24)
    mcp = tool_host(tools, streamable_http_path=f"/{token}/mcp",
                    stateless_http=True, json_response=True)
    sock = socket.socket()
    up = False
    try:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        # log_config=None: в оконной сборке sys.stdout пуст, а журнал uvicorn по
        # умолчанию спрашивает у него isatty. Записи идут в корневой журнал приложения.
        server = uvicorn.Server(uvicorn.Config(
            mcp.streamable_http_app(), log_config=None, timeout_graceful_shutdown=_CLOSE_SEC,
        ))
        task = asyncio.create_task(server.serve(sockets=[sock]))
        await _started(server, task)
        up = True
    finally:
        # Не поднявшийся сервер не закроет сокет сам.
        if not up:
            sock.close()
    return ToolServer(f"http://127.0.0.1:{port}/{token}/mcp", server, task)


async def _started(server: uvicorn.Server, task: asyncio.Task) -> None:
    deadline = asyncio.get_running_loop().time() + _START_SEC
    while not server.started:
        if task.done():
            task.result()
            raise RuntimeError("MCP-сервер закончил работу, не начав")
        if asyncio.get_running_loop().time() > deadline:
            task.cancel()
            raise TimeoutError("MCP-сервер не поднялся")
        await asyncio.sleep(0.01)
