"""Сессия агента: отдельный процесс Claude Code с инструментами приложения."""

import dataclasses
import json
import subprocess

from adapters.claude_code_agent import AgentRun, _argv, run_agent
from backend.agent.prompts.applier import APPLIER_PROMPT
from backend.agent.prompts.frame import system_prompt
from tests.fakes import claude_code

RUN = AgentRun(system_prompt="РАМКА", task="ЗАДАНИЕ", mcp_url="http://127.0.0.1:1/t/mcp",
               model="opus", web_search=False)


async def test_the_agent_gets_only_the_app_tools(monkeypatch):
    calls = claude_code.install(monkeypatch, [claude_code.result("готово")])

    await run_agent(RUN)

    argv = calls.spawned[0].argv
    assert argv[argv.index("--tools") + 1] == ""
    assert argv[argv.index("--allowedTools") + 1] == "mcp__jobbot"
    config = json.loads(argv[argv.index("--mcp-config") + 1])
    assert config["mcpServers"]["jobbot"]["url"] == RUN.mcp_url
    assert {"--strict-mcp-config", "--no-session-persistence"} <= set(argv)
    assert argv[argv.index("--setting-sources") + 1] == ""
    assert argv[argv.index("--system-prompt") + 1] == "РАМКА"


async def test_web_search_is_the_only_builtin_it_may_get(monkeypatch):
    calls = claude_code.install(monkeypatch, [claude_code.result("готово")])

    await run_agent(dataclasses.replace(RUN, web_search=True))

    argv = calls.spawned[0].argv
    assert argv[argv.index("--tools") + 1] == "WebSearch"
    assert argv[argv.index("--allowedTools") + 1] == "mcp__jobbot,WebSearch"


async def test_a_tool_call_may_wait_for_a_person_longer_than_an_hour(monkeypatch):
    calls = claude_code.install(monkeypatch, [claude_code.result("готово")])

    await run_agent(RUN)

    assert int(calls.spawned[0].env["MCP_TOOL_TIMEOUT"]) > 3600 * 1000


async def test_the_task_is_the_first_message_and_the_process_is_closed(monkeypatch):
    calls = claude_code.install(monkeypatch, [claude_code.result("готово")])

    end = await run_agent(RUN)

    assert calls.messages == ["ЗАДАНИЕ"]
    assert calls.killed == 1
    assert (end.ok, end.limit_exhausted) == (True, False)


async def test_an_exhausted_subscription_is_told_apart(monkeypatch):
    claude_code.install(monkeypatch, [claude_code.failure("usage limit reached", status=429)])

    end = await run_agent(RUN)

    assert (end.ok, end.limit_exhausted) == (False, True)


async def test_the_limit_is_told_by_its_words_when_the_status_is_missing(monkeypatch):
    """Статус 429 Claude Code даёт не всегда — тогда лимит узнаётся по тексту беды."""
    claude_code.install(monkeypatch, [claude_code.failure("Claude usage limit reached")])

    end = await run_agent(RUN)

    assert (end.ok, end.limit_exhausted) == (False, True)


async def test_a_plain_failure_is_not_taken_for_the_limit(monkeypatch):
    claude_code.install(monkeypatch, [claude_code.failure("сеть недоступна", status=500)])

    end = await run_agent(RUN)

    assert (end.ok, end.limit_exhausted) == (False, False)


async def test_a_dead_process_is_a_failed_session_not_a_crash(monkeypatch):
    calls = claude_code.install(monkeypatch, [claude_code.DIES])

    end = await run_agent(RUN)

    assert end.ok is False and end.limit_exhausted is False
    assert calls.killed == 1


async def test_without_claude_code_the_session_fails_without_a_process(monkeypatch):
    calls = claude_code.install(monkeypatch, [], cli=None)

    end = await run_agent(RUN)

    assert end.ok is False and calls.spawned == []


def test_the_longest_prompt_fits_a_windows_command_line():
    """Командная строка Windows — 32 767 знаков, а наставление откликателя самое длинное."""
    run = dataclasses.replace(RUN, system_prompt=system_prompt(APPLIER_PROMPT), web_search=True)

    assert len(subprocess.list2cmdline(_argv("claude", run))) < 30_000
