"""Следствия разговора с Claude через живой процесс Claude Code по подписке.

Зовущие видят только `lm_studio.make_client`, `lm_chat.chat` и `lm_models`,
поэтому и проверки идут через них: адрес `claude-code` в настройках должен
сам привести к обмену с процессом Claude Code. Подменены только поиск `claude`
и запуск процесса; выбор настоящего `claude.exe` проверяется отдельно.
"""

import asyncio
import logging
import os
import sys

import pytest

from adapters import claude_code, claude_code_process, lm_models
from adapters.claude_code import ClaudeCodeClient
from adapters.claude_code_process import _spawn as real_spawn
from adapters.lm_chat import chat
from adapters.lm_studio import make_client
from backend.provider_config import LlmProviderConfig
from tests.fakes.claude_code import CLI, DIES, HANGS, failure, install, result
from tests.fakes.llm import chat_request

LOG = logging.getLogger("tests.claude_code")
SONNET = "sonnet"


def _client() -> ClaudeCodeClient:
    return make_client(LlmProviderConfig("claude-code", "", SONNET))


def _model_of(process) -> str:
    """С какой моделью поднят процесс."""
    return process.argv[process.argv.index("--model") + 1]


async def test_claude_code_runs_quietly_in_streaming_mode(monkeypatch):
    """Процесс поднимается потоковым и без рабочего места разработчика.

    Инструменты, сохранение сессии, свои настройки и MCP выключены: модели
    нужен чистый разговор, а не рабочее место с его хуками и инструкциями.
    """
    calls = install(monkeypatch, [result("ок")])

    await chat(_client(), SONNET, chat_request(), LOG)

    argv = calls.spawned[0].argv
    assert argv[0] == CLI and "-p" in argv
    assert argv[argv.index("--input-format") + 1] == "stream-json"
    assert argv[argv.index("--output-format") + 1] == "stream-json"
    assert "--verbose" in argv
    assert _model_of(calls.spawned[0]) == SONNET
    assert argv[argv.index("--tools") + 1] == ""
    assert argv[argv.index("--setting-sources") + 1] == ""
    assert {"--no-session-persistence", "--strict-mcp-config"} <= set(argv)


async def test_the_rules_go_in_the_instruction_frame_before_the_data(monkeypatch):
    """Правила обращения — в рамке инструкций в начале сообщения, данные — после.

    Системный промпт у живого процесса один на все обращения, и правила
    каждого обращения едут в самом сообщении. Постоянный промпт процесса
    объясняет модели, что первый блок в рамке — правила оператора.
    """
    calls = install(monkeypatch, [result("ок")])

    await chat(_client(), SONNET, chat_request(), LOG)

    sent = calls.messages[0]
    assert sent.startswith(claude_code_process.FRAME_OPEN)
    assert sent.index("правила") < sent.index(claude_code_process.FRAME_CLOSE) < sent.index("текст")
    argv = calls.spawned[0].argv
    assert claude_code_process.FRAME_OPEN in argv[argv.index("--system-prompt") + 1]


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

    env = calls.spawned[0].env
    assert not set(cut) & set(env)
    assert env["JOB_BOT_TEST_MARK"] == "остаётся"


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
        pytest.param(DIES, "llm_request_error: CliTrouble", id="процесс упал"),
        pytest.param(OSError("нельзя запустить"), "llm_request_error: CliTrouble", id="не запустился"),
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
    assert calls.spawned == []


async def test_one_process_serves_many_requests_with_a_reset_after_each(monkeypatch):
    """Процесс поднимается один раз, а после каждого обращения разговор сбрасывается.

    Запуск `claude.exe` стоит дороже самого ответа, а без сброса модель
    разбирала бы новую вакансию, видя все прошлые, и разговор ел бы лимит.
    """
    calls = install(monkeypatch, [result("раз"), result("два"), result("три")])

    answers = [(await chat(_client(), SONNET, chat_request(), LOG)).text for _ in range(3)]

    assert answers == ["раз", "два", "три"]
    assert len(calls.spawned) == 1
    assert calls.clears == 3


async def test_requests_at_once_take_turns_in_the_one_process(monkeypatch):
    """Обращения разом идут к процессу по очереди, ответы не путаются.

    Процесс ведёт один разговор: второе сообщение, ушедшее до итога первого,
    получило бы чужой ответ.
    """
    calls = install(monkeypatch, [result("раз"), result("два"), result("три")])

    answers = await asyncio.gather(*(chat(_client(), SONNET, chat_request(), LOG) for _ in range(3)))

    assert sorted(one.text for one in answers) == ["два", "раз", "три"]
    assert calls.overlapped is False


async def test_another_model_restarts_the_process(monkeypatch):
    """Сменилась модель — прежний процесс снимается, новый идёт с новой моделью."""
    calls = install(monkeypatch, [result("раз"), result("два")])

    await chat(_client(), SONNET, chat_request(), LOG)
    await chat(_client(), "opus", chat_request(), LOG)

    models = [_model_of(p) for p in calls.spawned]
    assert models == [SONNET, "opus"]
    assert calls.killed == 1


async def test_a_process_that_died_is_replaced_by_the_next_request(monkeypatch):
    """Процесс упал — обращение отвечает бедой, а следующее поднимает новый."""
    calls = install(monkeypatch, [DIES, result("живой")])

    first = await chat(_client(), SONNET, chat_request(), LOG)
    second = await chat(_client(), SONNET, chat_request(), LOG)

    assert first.error == "llm_request_error: CliTrouble"
    assert second.text == "живой"
    assert len(calls.spawned) == 2


async def test_a_silent_process_is_dropped_after_the_deadline(monkeypatch):
    """Процесс молчит дольше срока — он снимается, следующее обращение поднимает новый.

    Оставь его жить, следующий вопрос получил бы запоздалый ответ на прошлый.
    """
    calls = install(monkeypatch, [HANGS, result("живой")])

    first = await chat(_client(), SONNET, chat_request(timeout=0.05), LOG)
    second = await chat(_client(), SONNET, chat_request(), LOG)

    assert first.error == "llm_request_error: CliTrouble"
    assert calls.killed == 1
    assert second.text == "живой"
    assert len(calls.spawned) == 2


async def test_a_process_that_died_between_requests_is_replaced_before_the_next(monkeypatch):
    """Процесс умер между запросами — следующий запрос поднимает новый, а не пропадает.

    Ушедший в мёртвый процесс запрос пропал бы вместе с разбором вакансии.
    """
    calls = install(monkeypatch, [result("раз"), result("два")])
    await chat(_client(), SONNET, chat_request(), LOG)
    calls.spawned[0].returncode = 1

    answer = await chat(_client(), SONNET, chat_request(), LOG)

    assert answer.text == "два"
    assert len(calls.spawned) == 2


async def test_shutting_down_puts_out_the_process_and_raises_no_new_one(monkeypatch):
    """Закрытие приложения снимает процесс, и запрос после него нового не поднимает.

    Поднятый после закрытия процесс снимать было бы уже некому.
    """
    calls = install(monkeypatch, [result("ок")])
    await chat(_client(), SONNET, chat_request(), LOG)

    await claude_code_process.shutdown()
    late = await chat(_client(), SONNET, chat_request(), LOG)

    assert calls.killed == 1
    assert late.error == "llm_request_error: CliTrouble"
    assert len(calls.spawned) == 1


async def test_every_listed_model_is_one_the_check_accepts_by_name(monkeypatch):
    """Каждое имя из перечня проходит проверку и уходит в Claude Code как есть.

    Перечень — подсказка в окне; имя из него, не принятое проверкой или
    искажённое по дороге, человек выбрал бы и получил погасшую лампочку.
    """
    calls = install(monkeypatch, [result("pong") for _ in range(3)])
    listed = await lm_models.list_models(_client(), kind="chat")

    for name in listed:
        assert await lm_models.check_model(_client(), name, "chat") == (True, name)

    assert listed and [_model_of(p) for p in calls.spawned] == listed


async def test_a_probe_that_fails_fails_the_check(monkeypatch):
    """Проба не прошла — проверка отвечает причиной, а не исключением."""
    install(monkeypatch, [failure("Claude AI usage limit reached")])

    ok, detail = await lm_models.check_model(_client(), SONNET, "chat")

    assert not ok and "usage limit" in detail


def test_the_real_exe_beside_the_npm_shim_is_preferred(monkeypatch, tmp_path):
    """Рядом с `.cmd`-обёрткой npm запускается настоящий `claude.exe`.

    Через обёртку доводы шли бы сквозь разбор `cmd.exe`, а при снятии
    снимался бы `cmd.exe`, оставляя `claude.exe` под ним сиротой.
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


async def test_the_real_spawn_ties_the_process_to_the_app_and_reads_long_lines(monkeypatch):
    """Настоящий запуск привязывает процесс к приложению и читает строку длиннее 64 КБ.

    Строка потока — целый ответ модели, и длинный разбор вакансии в предел
    чтения по умолчанию не влез бы.
    """
    tied: list[int] = []
    monkeypatch.setattr(claude_code_process.app_tied_process, "tie_to_app", tied.append)
    long_line = 'print("x" * 100_000)'
    process = await real_spawn([sys.executable, "-c", long_line], dict(os.environ))

    line = await process.stdout.readline()
    await process.wait()

    assert tied == [process.pid]
    assert len(line.strip()) == 100_000

