"""Подделка Claude Code: живой процесс подменён, обмен с ним и разбор настоящие.

Подменены два входа: где лежит `claude` (`claude_code._find_cli`) и запуск
процесса (`claude_code_process.spawn_cli`). Подставной процесс говорит потоком
JSON-строк, как настоящий: на сообщение — строка начала и итог, на `/clear` —
весть о сбросе, строка начала и пустой итог. Каждую строку он отдаёт, уступив
петлю, как и настоящая труба: иначе обращения разом шли бы по очереди и без
замка. Всё между входами — флаги, рамка, окружение, очередь, сброс,
перезапуск — остаётся боевым.
"""

import asyncio
import json

from adapters import claude_code, claude_code_process

CLI = r"C:\fake\claude.exe"

# Заготовки поведения процесса вместо ответа.
DIES = "процесс закрыл вывод"
HANGS = "процесс молчит"


def _answer(text: str | None, **fields) -> dict:
    """Итог потокового Claude Code: текст и поля исхода."""
    return {"type": "result", "result": text, **fields}


def result(text: str | None, *, stop_reason: str = "end_turn") -> dict:
    """Итог удачного запроса."""
    return _answer(
        text, subtype="success", is_error=False, stop_reason=stop_reason, api_error_status=None
    )


def failure(text: str, *, status: int | None = None) -> dict:
    """Итог запроса, который не удался."""
    return _answer(
        text,
        subtype="error_during_execution",
        is_error=True,
        stop_reason=None,
        api_error_status=status,
    )


class _Stdin:
    def __init__(self, process) -> None:
        self.process = process

    def write(self, data: bytes) -> None:
        line = json.loads(data.decode("utf-8"))
        if line["message"]["content"] == "/clear" and self.process.calls.clear_breaks_pipe:
            raise OSError("труба закрыта: процесс умер после ответа")
        self.process.heard(line)

    async def drain(self) -> None:
        return None


class _Stdout:
    def __init__(self, process) -> None:
        self.process = process

    async def readline(self) -> bytes:
        return await self.process.next_line()


class Process:
    """Подставной живой Claude Code: отвечает заготовленным по очереди."""

    def __init__(self, calls, argv: list[str], env: dict) -> None:
        self.calls = calls
        self.argv = argv
        self.env = env
        self.returncode = None
        self.stdin = _Stdin(self)
        self.stdout = _Stdout(self)
        self._lines: asyncio.Queue = asyncio.Queue()

    def heard(self, line: dict) -> None:
        """Строка, ушедшая процессу: запомнить и подложить ответ."""
        text = line["message"]["content"]
        if self.calls.reading:
            self.calls.overlapped = True
        self.calls.reading = True
        if text == "/clear":
            self.calls.clears += 1
            if self.calls.clear_dies:
                self._lines.put_nowait(b"")
                return
            self._push({"type": "conversation_reset"})
            self._push({"type": "system", "subtype": "init"})
            self._push(result("", stop_reason=None))
            return
        self.calls.messages.append(text)
        reply = self.calls.replies.pop(0)
        if reply == DIES:
            self._lines.put_nowait(b"")
        elif reply != HANGS:
            self._push({"type": "system", "subtype": "init"})
            self._push(reply)

    def _push(self, message: dict) -> None:
        self._lines.put_nowait((json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8"))

    async def next_line(self) -> bytes:
        await asyncio.sleep(0)
        line = await self._lines.get()
        if not line or json.loads(line).get("type") == "result":
            self.calls.reading = False
        return line

    def kill(self) -> None:
        self.returncode = -9
        self.calls.killed += 1

    async def wait(self) -> int:
        return self.returncode


class Calls:
    """Что видел подставной Claude Code: запуски, сообщения, сбросы, снятия."""

    def __init__(self, replies: list) -> None:
        self.replies = list(replies)
        self.spawned: list[Process] = []
        self.messages: list[str] = []
        self.clears = 0
        self.killed = 0
        # Сообщение ушло, пока предыдущее ещё ждало итога: очередь не держит.
        self.reading = False
        self.overlapped = False
        # Сброс разговора не удаётся: процесс закрывает вывод на `/clear`.
        self.clear_dies = False
        # Процесс умер сразу после ответа: запись `/clear` в трубу падает.
        self.clear_breaks_pipe = False


def install(monkeypatch, replies: list, *, cli: str | None = CLI) -> Calls:
    """Подставить Claude Code, отвечающий по очереди заготовленным.

    Ответ — итог (`result`, `failure`), `DIES` или `HANGS`; `OSError` первым в
    очереди — процесс не запускается вовсе.
    """
    calls = Calls(replies)

    async def spawn(argv, env):
        if calls.replies and isinstance(calls.replies[0], OSError):
            raise calls.replies.pop(0)
        process = Process(calls, argv, env)
        calls.spawned.append(process)
        return process

    monkeypatch.setattr(claude_code, "_find_cli", lambda: cli)
    monkeypatch.setattr(claude_code_process, "spawn_cli", spawn)
    return calls
