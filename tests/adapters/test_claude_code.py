"""Следствия разговора с Claude через Claude Code по подписке.

Зовущие видят только `lm_studio.make_client`, `lm_chat.chat` и `lm_models`,
поэтому и проверки идут через них: адрес `claude-code` в настройках должен
сам привести к запуску `claude -p`. Подменены только поиск `claude` и запуск
процесса; выбор настоящего `claude.exe` проверяется отдельно, без запуска.
"""

import json
import logging

import pytest

from adapters import claude_code, lm_models
from adapters.claude_code import ClaudeCodeClient
from adapters.lm_chat import chat
from adapters.lm_studio import LLM_REQUEST_TIMEOUT_SEC, make_client
from backend.provider_config import LlmProviderConfig
from tests.fakes.claude_code import CLI, failure, install, result
from tests.fakes.llm import chat_request

LOG = logging.getLogger("tests.claude_code")
SONNET = "sonnet"


def _client() -> ClaudeCodeClient:
    return make_client(LlmProviderConfig("claude-code", "", SONNET))


async def test_the_request_runs_claude_quietly_with_the_prompt_apart(monkeypatch):
    """Правила уходят файлом системного промпта, текст — через stdin.

    Инструменты, сохранение сессии, свои настройки и MCP выключены: модели
    нужен чистый разговор, а не рабочее место разработчика с его хуками и
    инструкциями.
    """
    calls = install(monkeypatch, [result("ок")])

    await chat(_client(), SONNET, chat_request(), LOG)

    argv = calls.argv[0]
    assert argv[0] == CLI and "-p" in argv
    assert argv[argv.index("--output-format") + 1] == "json"
    assert argv[argv.index("--model") + 1] == SONNET
    assert argv[argv.index("--effort") + 1] in {"low", "medium", "high", "xhigh", "max"}
    assert argv[argv.index("--tools") + 1] == ""
    assert argv[argv.index("--setting-sources") + 1] == ""
    assert {"--no-session-persistence", "--strict-mcp-config", "--disable-slash-commands"} <= set(argv)
    assert calls.system[0] == "правила"
    assert calls.stdin[0] == "текст"


async def test_only_what_leads_past_the_subscription_is_cut_from_the_environment(monkeypatch):
    """Ключи API, чужой адрес и облачные поставщики процессу не передаются.

    С ними Claude Code ушёл бы мимо подписки, и человек платил бы за то, что
    считал входящим в Max. Остальное окружение доходит как есть: без пути и
    профиля пользователя Claude Code не нашёл бы своего входа.
    """
    cut = (
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_BASE_URL",
        "CLAUDE_CODE_USE_BEDROCK",
        "CLAUDE_CODE_USE_VERTEX",
        "CLAUDE_CODE_USE_FOUNDRY",
    )
    for name in cut:
        monkeypatch.setenv(name, "1")
    monkeypatch.setenv("JOB_BOT_TEST_MARK", "остаётся")
    calls = install(monkeypatch, [result("ок")])

    await chat(_client(), SONNET, chat_request(), LOG)

    assert not set(cut) & set(calls.env[0])
    assert calls.env[0]["JOB_BOT_TEST_MARK"] == "остаётся"


async def test_the_answer_is_the_result_text(monkeypatch):
    """В ответ идёт текст из `result`."""
    install(monkeypatch, [result("готово")])

    answer = await chat(_client(), SONNET, chat_request(), LOG)

    assert (answer.text, answer.error) == ("готово", None)


async def test_an_answer_cut_by_the_limit_reads_as_length(monkeypatch, caplog):
    """Обрыв по пределу читается как у остальных путей и оставляет имя в журнале."""
    install(monkeypatch, [result('{"a":', stop_reason="max_tokens")])

    with caplog.at_level(logging.WARNING, logger="tests.claude_code"):
        answer = await chat(_client(), SONNET, chat_request(), LOG)

    assert answer.finish_reason == "length"
    assert "разбор вакансии: модель упёрлась в предел токенов" in caplog.text


async def test_a_refusal_is_an_error_not_an_empty_answer(monkeypatch):
    """Отказ модели — ошибка: пустой текст зовущий прочёл бы приговором объявлению."""
    install(monkeypatch, [result(None, stop_reason="refusal")])

    answer = await chat(_client(), SONNET, chat_request(), LOG)

    assert (answer.text, answer.error) == (None, "refusal")


@pytest.mark.parametrize(
    ("reply", "error"),
    [
        pytest.param(failure("rate limited", status=429), "llm_http_error: 429", id="ошибка API"),
        pytest.param(
            failure("Claude AI usage limit reached"),
            "llm_request_error: CliTrouble",
            id="лимит подписки",
        ),
        pytest.param((1, "", "boom"), "llm_request_error: CliTrouble", id="процесс упал"),
        pytest.param(
            (1, json.dumps(result("ок")), ""),
            "llm_request_error: CliTrouble",
            id="ответ при коде ошибки",
        ),
        pytest.param(OSError("нельзя запустить"), "llm_request_error: CliTrouble", id="не запустился"),
        pytest.param((0, "не json", ""), "llm_request_error: CliTrouble", id="ответ не разобрать"),
        pytest.param(TimeoutError(), "llm_request_error: CliTrouble", id="срок вышел"),
    ],
)
async def test_troubles_carry_the_same_marks_as_the_other_paths(monkeypatch, reply, error):
    """Беды Claude Code названы метками остальных путей, по ним зовущие выбирают откат."""
    install(monkeypatch, [reply])

    answer = await chat(_client(), SONNET, chat_request(), LOG)

    assert (answer.text, answer.error) == (None, error)


async def test_without_claude_code_installed_nothing_is_run(monkeypatch):
    """Claude Code не установлен — отказ без попытки что-то запустить."""
    calls = install(monkeypatch, [], cli=None)

    answer = await chat(_client(), SONNET, chat_request(), LOG)
    ok, detail = await lm_models.check_model(_client(), SONNET, "chat")

    assert answer.error == "llm_request_error: CliTrouble"
    assert not ok and "Claude Code" in detail
    assert calls.argv == []


async def test_the_deadline_of_the_app_or_of_the_request_reaches_the_process(monkeypatch):
    """Срок ожидания — общий у приложения либо свой у обращения."""
    calls = install(monkeypatch, [result("ок"), result("ок")])

    await chat(_client(), SONNET, chat_request(), LOG)
    await chat(_client(), SONNET, chat_request(timeout=300.0), LOG)

    assert calls.timeout == [LLM_REQUEST_TIMEOUT_SEC, 300.0]


async def test_every_listed_model_is_one_the_check_accepts_by_name(monkeypatch):
    """Каждое имя из перечня проходит проверку и уходит в Claude Code как есть.

    Перечень — подсказка в окне; имя из него, не принятое проверкой или
    искажённое по дороге, человек выбрал бы и получил погасшую лампочку.
    """
    calls = install(monkeypatch, [result("pong") for _ in range(3)])
    listed = await lm_models.list_models(_client(), kind="chat")

    for name in listed:
        assert await lm_models.check_model(_client(), name, "chat") == (True, name)

    assert listed and [argv[argv.index("--model") + 1] for argv in calls.argv] == listed


async def test_a_listed_model_that_answers_passes_the_check(monkeypatch):
    """Модель из перечня отвечает на пробу — проверка проходит."""
    calls = install(monkeypatch, [result("pong")])

    assert await lm_models.check_model(_client(), SONNET, "chat") == (True, SONNET)
    assert len(calls.argv) == 1


async def test_a_probe_that_fails_fails_the_check(monkeypatch):
    """Проба не прошла — проверка отвечает причиной, а не исключением."""
    install(monkeypatch, [failure("Claude AI usage limit reached")])

    ok, detail = await lm_models.check_model(_client(), SONNET, "chat")

    assert not ok and "usage limit" in detail


def test_the_real_exe_beside_the_npm_shim_is_preferred(monkeypatch, tmp_path):
    """Рядом с `.cmd`-обёрткой npm запускается настоящий `claude.exe`.

    Через обёртку доводы шли бы сквозь разбор `cmd.exe`, а по сроку снимался
    бы `cmd.exe`, оставляя `claude.exe` под ним сиротой.
    """
    shim = tmp_path / "claude.cmd"
    shim.write_text("@echo off")
    exe = tmp_path / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"MZ")
    monkeypatch.setattr(claude_code.shutil, "which", lambda _name: str(shim))

    assert claude_code._find_cli() == str(exe)


def test_without_an_exe_beside_the_found_claude_is_used(monkeypatch, tmp_path):
    """Нет `claude.exe` рядом — запускается найденный в PATH, как есть."""
    found = tmp_path / "claude.exe"
    found.write_bytes(b"MZ")
    monkeypatch.setattr(claude_code.shutil, "which", lambda _name: str(found))

    assert claude_code._find_cli() == str(found)

