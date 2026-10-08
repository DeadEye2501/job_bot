"""Claude через установленный Claude Code по подписке: запросы и перечень моделей.

Надстройка рядом с OpenAI-совместимым путём и с API Anthropic (`adapters/claude`):
API оплачивается отдельно от подписки, а Claude Code ходит под входом
человека в Max. Точки входа (`lm_studio`, `lm_chat`, `lm_models`) узнают этот
клиент по типу. Здесь — из чего складывается сообщение и что берётся из
ответа; живой процесс, через который идут запросы, — в `adapters/claude_code_process`.
"""

import shutil
from pathlib import Path

from adapters import claude_code_process
from adapters.claude import FINISH, split_system

# Имена, которые Claude Code сам ведёт к последней версии модели.
MODELS = ["sonnet", "opus", "haiku"]

NO_CLI = "Claude Code не установлен"


class CliTrouble(Exception):
    """Claude Code не ответил: не установлен, упал, не уложился в срок или вернул ошибку.

    `status` — код ответа API, когда беда пришла от него; по нему метка та же,
    что у остальных путей.
    """

    def __init__(self, detail: str, status: int | None = None) -> None:
        super().__init__(detail)
        self.status = status


class ClaudeCodeClient:
    """Клиент Claude Code: помнит срок ожидания, процесс у всех клиентов общий."""

    def __init__(self, timeout: float) -> None:
        self.timeout = timeout

    async def aclose(self) -> None:
        """Закрывать нечего: процесс живёт до закрытия окна, а не клиента."""


def make_client(*, timeout: float) -> ClaudeCodeClient:
    """Клиент Claude Code; ключа и адреса у него нет, вход — подписка человека."""
    return ClaudeCodeClient(timeout=timeout)


def _find_cli() -> str | None:
    """Путь к `claude.exe`; пусто — Claude Code не установлен.

    npm кладёт в PATH `.cmd`-обёртку. Через неё доводы шли бы сквозь разбор
    `cmd.exe`, а при снятии снимался бы `cmd.exe`, оставляя под ним сироту,
    поэтому берётся настоящий `claude.exe` рядом с ней.
    """
    found = shutil.which("claude")
    if found is None:
        return None
    beside = Path(found).parent / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"
    return str(beside) if beside.is_file() else found


def _cli() -> str:
    """Путь к Claude Code, а нет его — отказ одной фразой на всех зовущих."""
    cli = _find_cli()
    if cli is None:
        raise CliTrouble(NO_CLI)
    return cli


def _reply(data: dict) -> tuple[str | None, str | None]:
    """Текст и причина конца из итога обращения; беда — `CliTrouble`."""
    if data.get("is_error"):
        detail = data.get("result") or data.get("subtype") or "ошибка без описания"
        raise CliTrouble(str(detail)[:200], status=data.get("api_error_status"))
    stop = data.get("stop_reason")
    return data.get("result"), FINISH.get(stop, stop)


async def _converse(
    client: ClaudeCodeClient, model: str, messages: list[dict], timeout: float | None
) -> tuple[str | None, str | None]:
    """Одно обращение: правила — в рамке инструкций, реплики — данными после неё."""
    cli = _cli()
    system, turns = split_system(messages)
    message = claude_code_process.framed(system, "\n\n".join(m["content"] for m in turns))
    try:
        data = await claude_code_process.exchange(cli, model, message, timeout or client.timeout)
    except (TimeoutError, OSError, claude_code_process.ProcessGone) as e:
        raise CliTrouble(f"{type(e).__name__}: {e}") from e
    return _reply(data)


async def ask(client: ClaudeCodeClient, model: str, request):
    """Спросить модель: текст и причина конца в словаре OpenAI.

    `request` — `lm_chat.ChatRequest`; тип не назван, потому что `lm_chat` сам
    зовёт этот модуль. Беды уходят наверх `CliTrouble`: метку им ставит
    `lm_chat`, одну на все пути. Отказ модели приходит причиной конца, как у API.
    """
    return await _converse(client, model, request.messages, request.timeout)


async def list_models(_client: ClaudeCodeClient) -> list[str]:
    """Модели Claude Code. Нет Claude Code — `CliTrouble`."""
    _cli()
    return list(MODELS)


async def ping(client: ClaudeCodeClient, model: str, text: str) -> None:
    """Пробный запрос через Claude Code; беда — `CliTrouble`."""
    await _converse(client, model, [{"role": "user", "content": text}], None)
