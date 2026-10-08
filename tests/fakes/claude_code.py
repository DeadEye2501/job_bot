"""Подделка Claude Code: запуск процесса подменён, разбор и сборка вызова настоящие.

Подменены два входа: где лежит `claude` (`_find_cli`) и сам запуск процесса
(`_run_cli`). Всё между ними — флаги, файл системного промпта, окружение,
разбор ответа — остаётся боевым, и тесты видят, что ушло бы в процесс.
"""

import json
from pathlib import Path

from adapters import claude_code

CLI = r"C:\fake\claude.exe"


def _answer(text: str | None, **fields) -> dict:
    """Ответ `claude -p --output-format json`: текст и поля исхода."""
    return {"type": "result", "result": text, **fields}


def result(text: str | None, *, stop_reason: str = "end_turn") -> dict:
    """Ответ Claude Code на удачный запрос."""
    return _answer(
        text, subtype="success", is_error=False, stop_reason=stop_reason, api_error_status=None
    )


def failure(text: str, *, status: int | None = None) -> dict:
    """Ответ Claude Code, в котором запрос не удался."""
    return _answer(
        text,
        subtype="error_during_execution",
        is_error=True,
        stop_reason=None,
        api_error_status=status,
    )


class Calls:
    """Что ушло бы в процесс: доводы, stdin, окружение, срок и системный промпт."""

    def __init__(self) -> None:
        self.argv: list[list[str]] = []
        self.stdin: list[str] = []
        self.env: list[dict] = []
        self.timeout: list[float] = []
        self.system: list[str] = []


def _system_prompt(argv: list[str]) -> str:
    """Текст файла системного промпта, пока адаптер его не удалил."""
    return Path(argv[argv.index("--system-prompt-file") + 1]).read_text(encoding="utf-8")


def install(monkeypatch, replies: list, *, cli: str | None = CLI) -> Calls:
    """Подставить Claude Code, отвечающий по очереди заготовленным.

    Ответ — словарь (уйдёт в stdout как JSON), тройка «код, stdout, stderr»
    или исключение. Системный промпт читается в миг вызова: после ответа
    адаптер свой временный файл удаляет.
    """
    calls = Calls()
    queue = list(replies)

    async def run(argv, stdin, env, timeout):
        calls.argv.append(argv)
        calls.stdin.append(stdin)
        calls.env.append(env)
        calls.timeout.append(timeout)
        calls.system.append(_system_prompt(argv))
        reply = queue.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        if isinstance(reply, tuple):
            return reply
        return 0, json.dumps(reply, ensure_ascii=False), ""

    monkeypatch.setattr(claude_code, "_find_cli", lambda: cli)
    monkeypatch.setattr(claude_code, "_run_cli", run)
    return calls
