"""Сессия агента в своём процессе Claude Code: инструменты приложения, без чужих настроек."""

import json
import logging
import re
from dataclasses import dataclass

from adapters import claude_code, claude_code_process
from adapters.agent_mcp import SERVER_NAME

logger = logging.getLogger(__name__)

_TOOL_TIMEOUT_MS = 65 * 60 * 1000
_LIMIT_STATUS = 429
# Признака «исчерпан лимит подписки» Claude Code не даёт; статус 429 приходит
# не всегда, и тогда остаются слова в тексте беды.
_LIMIT_RE = re.compile(r"usage limit|limit reached|rate limit", re.IGNORECASE)


@dataclass(frozen=True)
class AgentEnd:
    """Итог процесса агента: дошёл ли он до конца, что сказал, исчерпан ли лимит подписки."""

    ok: bool
    detail: str
    limit_exhausted: bool


@dataclass(frozen=True)
class AgentRun:
    """Одна сессия: наставление, задание, адрес MCP-сервера её инструментов, модель, поиск в сети."""

    system_prompt: str
    task: str
    mcp_url: str
    model: str
    web_search: bool


async def run_agent(run: AgentRun) -> AgentEnd:
    """Одна сессия — один процесс. Процесс закрывается, чем бы сессия ни кончилась,
    в том числе отменой задачи.

    Запуск и обмен зовутся через модуль, а не ввезённым именем: подделка и
    запрет живого Claude Code в тестах подменяют их там же, где у чата.
    """
    try:
        process = await claude_code_process.spawn_cli(_argv(claude_code.cli(), run), _env())
    except (OSError, claude_code.CliTrouble) as e:
        logger.exception("агент не запустился")
        return AgentEnd(False, f"агент не запустился: {e}", False)
    try:
        return _end(await claude_code_process.one_turn(process, run.task))
    except (claude_code_process.ProcessGone, OSError) as e:
        logger.exception("процесс агента оборвался")
        return AgentEnd(False, f"процесс агента оборвался: {e}", False)
    finally:
        await claude_code_process.put_down(process)


def _end(data: dict) -> AgentEnd:
    """Итог сессии по итогу процесса; беду разбирает тот же `reply_of`, что у чата."""
    try:
        text, _finish = claude_code.reply_of(data)
    except claude_code.CliTrouble as trouble:
        detail = str(trouble)
        limit = trouble.status == _LIMIT_STATUS or bool(_LIMIT_RE.search(detail))
        return AgentEnd(False, detail, limit)
    return AgentEnd(True, text or "", False)


def _argv(cli: str, run: AgentRun) -> list[str]:
    """Доводы потокового разговора плюс инструменты приложения.

    `--allowedTools` обязателен: без него каждый вызов инструмента ждал бы
    разрешения, а в режиме `-p` дать его некому.
    """
    builtins = "WebSearch" if run.web_search else ""
    allowed = f"mcp__{SERVER_NAME}" + (",WebSearch" if run.web_search else "")
    config = json.dumps({"mcpServers": {SERVER_NAME: {"type": "http", "url": run.mcp_url}}})
    return [
        *claude_code_process.stream_argv(cli, run.model, run.system_prompt, builtins),
        "--allowedTools", allowed, "--mcp-config", config,
    ]


def _env() -> dict:
    """Окружение подписки и срок вызова инструмента дольше часа ожидания человека."""
    return {**claude_code_process.subscription_env(), "MCP_TOOL_TIMEOUT": str(_TOOL_TIMEOUT_MS)}
