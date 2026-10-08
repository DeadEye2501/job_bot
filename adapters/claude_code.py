"""Claude через установленный Claude Code по подписке: запрос — процесс `claude -p`.

Надстройка рядом с OpenAI-совместимым путём и с API Anthropic (`adapters/claude`):
API оплачивается отдельно от подписки, а Claude Code ходит под входом
человека в Max. Точки входа (`lm_studio`, `lm_chat`, `lm_models`) узнают этот
клиент по типу. Метки бед и проверка ответа остаются общими у них.
"""

import asyncio
import json
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from adapters.claude import EFFORT, FINISH, REFUSED, split_system

CLAUDE_CODE_ADDRESS = "claude-code"

# Имена, которые Claude Code сам ведёт к последней версии модели.
MODELS = ["sonnet", "opus", "haiku"]

NO_CLI = "Claude Code не установлен"

# С ключом API, чужим адресом или облачным поставщиком в окружении Claude Code
# ушёл бы мимо подписки — человек платил бы за то, что считал входящим в Max.
_NOT_SUBSCRIPTION = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_BASE_URL",
    "CLAUDE_CODE_USE_BEDROCK",
    "CLAUDE_CODE_USE_VERTEX",
    "CLAUDE_CODE_USE_FOUNDRY",
)

# Окно процесса не показывается: приложение оконное, и каждый запрос мигал бы
# консолью поверх него.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class CliTrouble(Exception):
    """Claude Code не ответил: не установлен, упал, не уложился в срок или вернул ошибку.

    `status` — код ответа API, когда беда пришла от него; по нему метка та же,
    что у остальных путей.
    """

    def __init__(self, detail: str, status: int | None = None) -> None:
        super().__init__(detail)
        self.status = status


class ClaudeCodeClient:
    """Клиент Claude Code: помнит срок ожидания, процесс живёт ровно один запрос."""

    def __init__(self, timeout: float) -> None:
        self.timeout = timeout

    async def aclose(self) -> None:
        """Закрывать нечего: соседи закрывают клиента, и этот обязан уметь."""


def serves(base_url: str) -> bool:
    """Ведёт ли адрес к Claude Code."""
    return base_url.strip() == CLAUDE_CODE_ADDRESS


def make_client(*, timeout: float) -> ClaudeCodeClient:
    """Клиент Claude Code; ключа и адреса у него нет, вход — подписка человека."""
    return ClaudeCodeClient(timeout=timeout)


def _find_cli() -> str | None:
    """Путь к `claude.exe`; пусто — Claude Code не установлен.

    npm кладёт в PATH `.cmd`-обёртку. Через неё доводы шли бы сквозь разбор
    `cmd.exe`, поэтому берётся настоящий `claude.exe` рядом с ней.
    """
    found = shutil.which("claude")
    if found is None:
        return None
    beside = Path(found).parent / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"
    return str(beside) if beside.is_file() else found


def _argv(cli: str, model: str, prompt_file: str) -> list[str]:
    """Доводы запуска: чистый разговор без рабочего места разработчика.

    Инструменты, сохранение сессии, свои настройки с хуками, MCP и навыки
    выключены: модели нужны только наш промпт и текст.
    """
    return [
        cli, "-p",
        "--output-format", "json",
        "--model", model,
        "--effort", EFFORT,
        "--system-prompt-file", prompt_file,
        "--tools", "",
        "--setting-sources", "",
        "--no-session-persistence",
        "--strict-mcp-config",
        "--disable-slash-commands",
    ]


async def _run_cli(argv: list[str], stdin: str, env: dict, timeout: float) -> tuple[int, str, str]:
    """Запустить Claude Code и дождаться ответа; по сроку процесс снимается."""
    process = await asyncio.create_subprocess_exec(
        *argv,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
        cwd=tempfile.gettempdir(),
        creationflags=_NO_WINDOW,
    )
    try:
        out, err = await asyncio.wait_for(process.communicate(stdin.encode("utf-8")), timeout)
    finally:
        # И по сроку, и при отмене задачи — остановка бота отменяет её: иначе
        # `claude.exe` доживал бы запрос сиротой, тратя лимит подписки.
        if process.returncode is None:
            process.kill()
            await process.wait()
    return process.returncode, out.decode("utf-8", "replace"), err.decode("utf-8", "replace")


def _reply(code: int, stdout: str, stderr: str) -> tuple[str | None, str | None]:
    """Текст и причина конца из JSON-ответа; беда — `CliTrouble`."""
    try:
        data = json.loads(stdout)
    except ValueError as e:
        raise CliTrouble(f"ответ не разобрать (код {code}): {stderr[:200]}") from e
    if data.get("is_error") or code != 0:
        detail = data.get("result") or data.get("subtype") or f"код {code}: {stderr[:200]}"
        raise CliTrouble(str(detail)[:200], status=data.get("api_error_status"))
    stop = data.get("stop_reason")
    if stop == REFUSED:
        return None, REFUSED
    return data.get("result"), FINISH.get(stop, stop)


async def _converse(
    client: ClaudeCodeClient, model: str, messages: list[dict], timeout: float | None
) -> tuple[str | None, str | None]:
    """Один запрос: системный промпт — во временный файл, реплики — в stdin."""
    cli = _find_cli()
    if cli is None:
        raise CliTrouble(NO_CLI)
    system, turns = split_system(messages)
    text = "\n\n".join(m["content"] for m in turns)
    env = {k: v for k, v in os.environ.items() if k not in _NOT_SUBSCRIPTION}
    with tempfile.TemporaryDirectory() as folder:
        prompt_file = os.path.join(folder, "system.txt")
        Path(prompt_file).write_text(system, encoding="utf-8")
        try:
            code, out, err = await _run_cli(
                _argv(cli, model, prompt_file), text, env, timeout or client.timeout
            )
        except (TimeoutError, OSError) as e:
            raise CliTrouble(f"{type(e).__name__}: {e}") from e
    return _reply(code, out, err)


async def ask(client: ClaudeCodeClient, model: str, request, log: logging.Logger):
    """Спросить модель: текст и причина конца в словаре OpenAI.

    `request` — `lm_chat.ChatRequest`; тип не назван, потому что `lm_chat` сам
    зовёт этот модуль. Беды уходят наверх `CliTrouble`: метку им ставит
    `lm_chat`, одну на все пути. Отказ модели — ответ без текста с `REFUSED`.
    """
    text, finish = await _converse(client, model, request.messages, request.timeout)
    if finish == REFUSED:
        log.warning("%s: модель отказалась отвечать", request.purpose)
    return text, finish


async def list_models(_client: ClaudeCodeClient, kind: str | None = None) -> list[str]:
    """Модели Claude Code; эмбеддингов он не даёт. Нет Claude Code — `CliTrouble`."""
    if kind == "embed":
        return []
    if _find_cli() is None:
        raise CliTrouble(NO_CLI)
    return list(MODELS)


async def ping(client: ClaudeCodeClient, model: str) -> tuple[bool, str]:
    """Пробный запрос через Claude Code — для кнопки проверки связи."""
    try:
        await _converse(client, model, [{"role": "user", "content": "ping"}], None)
    except CliTrouble as e:
        return False, f"{model} (ping failed: {e})"
    return True, model
