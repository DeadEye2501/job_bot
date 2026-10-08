"""Следствия разговора с Claude через нынешние точки входа адаптеров.

Зовущие видят только `lm_studio.make_client`, `lm_chat.chat` и `lm_models`,
поэтому и проверки идут через них: клиент Anthropic должен попасть в свой
адаптер сам, по одному адресу в настройках. Подделан транспорт, а не SDK:
тело запроса и разбор ответа остаются настоящими.
"""

import json
import logging

import httpx2
import pytest

from adapters import lm_models
from adapters.lm_chat import chat
from adapters.lm_studio import LLM_REQUEST_TIMEOUT_SEC, make_client
from backend.provider_config import LlmProviderConfig
from tests.fakes.claude import MESSAGES, MODELS, claude, message, model_list, refusal
from tests.fakes.llm import chat_request, handler

LOG = logging.getLogger("tests.claude")
SONNET = "claude-sonnet-5-5"


def _body(client) -> dict:
    """Тело последнего запроса, ушедшего к поддельному Anthropic."""
    return json.loads(client.sent[-1].content)


@pytest.fixture
def wire(monkeypatch):
    """Настоящий клиент из `make_client`, но транспорт отвечает заготовленным.

    Подделка `claude()` собирает клиента сама, мимо `make_client`, и того, что
    делает боевая сборка — ключ, адрес, срок ожидания, — не видит. Здесь
    подменяется сам транспорт `httpx2`, поверх запора стенда.
    """

    def install(routes: dict) -> list:
        sent: list = []
        mock = httpx2.MockTransport(handler(routes, sent, httpx2))

        async def relay(_transport, request):
            return await mock.handle_async_request(request)

        monkeypatch.setattr(httpx2.AsyncHTTPTransport, "handle_async_request", relay)
        return sent

    return install


async def test_the_key_from_settings_goes_out_as_the_anthropic_header(wire):
    """Ключ из настроек уходит заголовком `x-api-key`, со сроком ожидания приложения."""
    sent = wire({MESSAGES: message("ок")})
    client = make_client(LlmProviderConfig("https://api.anthropic.com", "sk-1", SONNET))

    await chat(client, SONNET, chat_request(), LOG)
    await client.aclose()

    assert sent[-1].headers["x-api-key"] == "sk-1"
    assert sent[-1].extensions["timeout"]["read"] == LLM_REQUEST_TIMEOUT_SEC


async def test_an_address_typed_with_v1_still_reaches_the_messages_path(wire):
    """Адрес, набранный с `/v1`, не превращается в `/v1/v1/messages`.

    Такой запрос получил бы 404, и человек искал бы пропавшую модель, а не
    лишний хвост в адресе.
    """
    sent = wire({MESSAGES: message("ок")})
    client = make_client(LlmProviderConfig("https://api.anthropic.com/v1", "sk-1", SONNET))

    answer = await chat(client, SONNET, chat_request(), LOG)
    await client.aclose()

    assert answer.text == "ок"
    assert sent[-1].url.path == "/v1/messages"


async def test_an_empty_key_is_refused_without_the_environment_one(wire, monkeypatch):
    """Пустой ключ — отказ без похода в сеть; ключ из окружения не подхватывается.

    Подхвати SDK его, приложение ходило бы к модели за чужой счёт, а человек
    видел бы в настройках пустое поле ключа и работающий чат. А упади запрос
    исключением, оно ушло бы мимо всех откатов зовущих.
    """
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-из-окружения")
    sent = wire({MESSAGES: message("ок")})
    client = make_client(LlmProviderConfig("https://api.anthropic.com", "", SONNET))

    answer = await chat(client, SONNET, chat_request(), LOG)
    ok, detail = await lm_models.check_model(client, SONNET, "chat")
    await client.aclose()

    assert (answer.text, answer.error) == (None, "no_api_key")
    assert not ok and "ключ" in detail
    assert sent == []


async def test_the_system_prompt_travels_apart_from_the_turns():
    """Правила уходят параметром `system`, а в репликах остаётся только текст."""
    client = claude({MESSAGES: message("ок")})

    await chat(client, SONNET, chat_request(), LOG)

    body = _body(client)
    assert body["system"] == "правила"
    assert body["messages"] == [{"role": "user", "content": "текст"}]


async def test_no_temperature_is_sent_and_thinking_has_room():
    """Температура не уходит, размышление включено и предел поднят.

    Текущие модели отвечают на температуру отказом 400, а размышление тратит
    тот же предел, что и ответ: с пределом под локальную модель ответ
    обрывался бы, не начавшись.
    """
    client = claude({MESSAGES: message("ок")})

    await chat(client, SONNET, chat_request(temperature=0.5), LOG)

    body = _body(client)
    assert "temperature" not in body
    assert body["thinking"] == {"type": "adaptive"}
    assert "effort" in body["output_config"]
    assert body["max_tokens"] > 1200


async def test_the_answer_is_the_text_without_the_thinking():
    """В ответ идёт текст модели; блок размышления в него не попадает."""
    client = claude({MESSAGES: message("готово")})

    answer = await chat(client, SONNET, chat_request(), LOG)

    assert (answer.text, answer.error) == ("готово", None)


async def test_an_answer_cut_by_the_limit_reads_as_length_and_names_itself(caplog):
    """Обрыв по пределу читается как у OpenAI-пути и оставляет имя в журнале.

    По признаку `length` зовущие решают, разбирать ли обрезанный ответ и
    просить ли места больше; другое слово для того же они бы не узнали.
    """
    client = claude({MESSAGES: message('{"a":', stop_reason="max_tokens")})

    with caplog.at_level(logging.WARNING, logger="tests.claude"):
        answer = await chat(client, SONNET, chat_request(), LOG)

    assert answer.finish_reason == "length"
    assert "разбор вакансии: модель упёрлась в предел токенов" in caplog.text


async def test_an_exhausted_context_window_is_a_cut_answer_too():
    """Окно контекста, кончившееся посреди ответа, — тот же обрыв."""
    client = claude({MESSAGES: message('{"a":', stop_reason="model_context_window_exceeded")})

    answer = await chat(client, SONNET, chat_request(), LOG)

    assert answer.finish_reason == "length"


async def test_a_refusal_is_an_error_named_in_the_log(caplog):
    """Отказ модели — ошибка, а не пустой текст; в журнале видно, кто отказался.

    Пустой текст зовущий прочёл бы как «в объявлении ничего нет», и отказ
    модели превратился бы в приговор объявлению.
    """
    client = claude({MESSAGES: refusal("cyber")})

    with caplog.at_level(logging.WARNING, logger="tests.claude"):
        answer = await chat(client, SONNET, chat_request(), LOG)

    assert (answer.text, answer.error) == (None, "refusal")
    assert "разбор вакансии: модель отказалась отвечать" in caplog.text


@pytest.mark.parametrize(
    ("prepared", "error"),
    [
        pytest.param(
            httpx2.Response(
                500, json={"type": "error", "error": {"type": "api_error", "message": "x"}}
            ),
            "llm_http_error: 500",
            id="отказ кодом",
        ),
        pytest.param(
            httpx2.ConnectError("сеть отвалилась"),
            "llm_request_error: APIConnectionError",
            id="обрыв связи",
        ),
    ],
)
async def test_provider_troubles_carry_the_same_marks_as_the_openai_path(prepared, error):
    """Беды поставщика названы теми же метками, что у OpenAI-пути.

    По меткам зовущие выбирают откат, и незнакомая метка ушла бы мимо него.
    """
    client = claude({MESSAGES: prepared})

    answer = await chat(client, SONNET, chat_request(), LOG)

    assert (answer.text, answer.error) == (None, error)


async def test_a_request_with_its_own_deadline_carries_it():
    """Своё время ожидания обращения доезжает до запроса."""
    client = claude({MESSAGES: message("ок")})

    await chat(client, SONNET, chat_request(timeout=300.0), LOG)

    assert client.sent[-1].extensions["timeout"]["read"] == 300.0


async def test_chat_models_come_from_the_key():
    """Чатовые модели — те, что доступны ключу."""
    client = claude({MODELS: model_list(SONNET, "claude-haiku-5-5")})

    assert await lm_models.list_models(client, kind="chat") == [SONNET, "claude-haiku-5-5"]


async def test_a_listed_model_that_answers_passes_the_check():
    """Модель есть у ключа и отвечает на пробу с настоящими параметрами.

    Голая проба прошла бы и у модели, которая не принимает размышления, — и
    кнопка зеленела бы над чатом, где каждый запрос получает 400.
    """
    client = claude({MODELS: model_list(SONNET), MESSAGES: message("pong")})

    assert await lm_models.check_model(client, SONNET, "chat") == (True, SONNET)
    assert _body(client)["thinking"] == {"type": "adaptive"}


async def test_a_listed_model_whose_probe_fails_fails_the_check():
    """Модель числится, но на пробу отвечает отказом — проверка не проходит."""
    refused = httpx2.Response(
        400, json={"type": "error", "error": {"type": "invalid_request_error", "message": "x"}}
    )
    client = claude({MODELS: model_list(SONNET), MESSAGES: refused})

    ok, detail = await lm_models.check_model(client, SONNET, "chat")

    assert not ok and "ping failed" in detail


async def test_an_unlisted_model_fails_the_check_by_name():
    """Модели нет у ключа — отказ называет её, а в сеть с пробой не ходят."""
    client = claude({MODELS: model_list("claude-haiku-5-5")})

    ok, detail = await lm_models.check_model(client, SONNET, "chat")

    assert not ok and SONNET in detail
    assert [request.url.path for request in client.sent] == ["/v1/models"]


async def test_closing_the_client_closes_its_connection():
    """Закрытие тем же `aclose`, что у httpx-клиентов соседей, закрывает SDK."""
    client = claude({})

    await client.aclose()

    assert client.is_closed()
