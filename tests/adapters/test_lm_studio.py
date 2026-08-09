"""Следствия, которые наблюдают тесты `adapters/lm_studio.py`.

Модуль — тонкая прослойка к любому провайдеру, совместимому с OpenAI. Его
работа целиком состоит из того, что уходит в запросе и что получается из
ответа, поэтому подделан транспорт, а не клиент: заголовки, пути и разбор
JSON остаются настоящими.
"""

import httpx
import pytest

from adapters.lm_studio import check_chat, check_embed, embed, list_models, make_client
from backend.runtime_settings import LlmProviderConfig
from tests.fakes.llm import CHAT, models_response, provider

MODELS = ("GET", "/v1/models")
NATIVE_MODELS = ("GET", "/api/v0/models")
EMBEDDINGS = ("POST", "/v1/embeddings")


def test_a_provider_without_a_key_gets_no_authorization_header():
    """Локальному провайдеру заголовок с ключом не отправляется."""
    client = make_client(LlmProviderConfig("http://localhost:1234", "", "qwen"))
    assert "Authorization" not in client.headers


def test_a_key_from_settings_becomes_a_bearer_header():
    """Ключ из настроек уходит в заголовок в форме Bearer."""
    client = make_client(LlmProviderConfig("https://api.test", "sk-123", "gpt"))
    assert client.headers["Authorization"] == "Bearer sk-123"


def test_the_base_url_from_settings_is_used():
    """Адрес провайдера берётся из настроек."""
    client = make_client(LlmProviderConfig("https://api.test", "", "gpt"))
    assert str(client.base_url) == "https://api.test"


async def test_a_loaded_chat_model_passes_the_check():
    """Модель есть в списке и отвечает на пинг — проверка пройдена."""
    client = provider({
        MODELS: models_response("qwen", "llama"),
        CHAT: httpx.Response(200, json={"choices": []}),
    })
    assert await check_chat(client, "qwen") == (True, "qwen")


async def test_a_missing_chat_model_fails_the_check_and_lists_what_there_is():
    """Если модели нет, отказ называет, что у провайдера есть."""
    client = provider({MODELS: models_response("llama", "mistral")})
    passed, message = await check_chat(client, "qwen")
    assert passed is False
    assert "llama" in message and "mistral" in message


async def test_a_provider_with_no_models_says_so_plainly():
    """Пустой список моделей называется словами, а не пустой строкой."""
    client = provider({MODELS: models_response()})
    passed, message = await check_chat(client, "qwen")
    assert passed is False
    assert "no models loaded" in message


async def test_a_chat_model_that_fails_the_ping_does_not_pass():
    """Модель в списке есть, но пинг не прошёл — проверка не пройдена."""
    client = provider({
        MODELS: models_response("qwen"),
        CHAT: httpx.Response(500, text="сломалось"),
    })
    passed, message = await check_chat(client, "qwen")
    assert passed is False
    assert "500" in message


async def test_a_provider_error_response_names_its_kind_and_code():
    """Провайдер ответил ошибкой на список моделей — сообщение называет её род и код."""
    client = provider({})
    passed, message = await check_chat(client, "qwen")
    assert passed is False
    assert "HTTPStatusError" in message
    assert "599" in message


async def test_a_loaded_embedding_model_passes_the_check():
    """Модель встраиваний есть и отвечает — проверка пройдена."""
    client = provider({
        MODELS: models_response("bge-m3"),
        EMBEDDINGS: httpx.Response(200, json={"data": [{"embedding": [0.1]}]}),
    })
    assert await check_embed(client, "bge-m3") == (True, "bge-m3")


async def test_a_missing_embedding_model_fails_the_check():
    """Отсутствующая модель встраиваний проверку не проходит."""
    client = provider({MODELS: models_response("qwen")})
    passed, _ = await check_embed(client, "bge-m3")
    assert passed is False


async def test_an_embedding_model_that_fails_the_ping_does_not_pass():
    """Модель встраиваний в списке есть, но пинг не прошёл — проверка не пройдена."""
    client = provider({
        MODELS: models_response("bge-m3"),
        EMBEDDINGS: httpx.Response(500, text="сломалось"),
    })
    passed, message = await check_embed(client, "bge-m3")
    assert passed is False
    assert "500" in message


async def test_all_model_ids_come_back_when_no_kind_is_asked_for():
    """Без указания рода возвращается весь список провайдера."""
    client = provider({MODELS: models_response("qwen", "bge-m3")})
    assert await list_models(client) == ["qwen", "bge-m3"]


async def test_only_loaded_models_of_the_asked_kind_come_back():
    """У LM Studio берутся только загруженные модели нужного рода."""
    client = provider({
        NATIVE_MODELS: httpx.Response(200, json={"data": [
            {"id": "qwen", "state": "loaded", "type": "llm"},
            {"id": "llama", "state": "not-loaded", "type": "llm"},
            {"id": "bge-m3", "state": "loaded", "type": "embeddings"},
        ]}),
    })
    assert await list_models(client, kind="chat") == ["qwen"]
    assert await list_models(client, kind="embed") == ["bge-m3"]


async def test_a_provider_without_the_native_endpoint_falls_back_by_name():
    """Если родного пути нет, род угадывается по имени модели."""
    client = provider({
        NATIVE_MODELS: httpx.Response(404, text="нет такого"),
        MODELS: models_response("qwen", "bge-m3", "text-embedding-ada-002"),
    })
    assert await list_models(client, kind="chat") == ["qwen"]
    assert await list_models(client, kind="embed") == [
        "bge-m3",
        "text-embedding-ada-002",
    ]


async def test_a_native_endpoint_answering_with_non_json_falls_back_by_name():
    """Родной путь ответил 200 не-JSON'ом — используется запасной путь по имени."""
    client = provider({
        NATIVE_MODELS: httpx.Response(200, text="not json"),
        MODELS: models_response("qwen", "bge-m3"),
    })
    assert await list_models(client, kind="chat") == ["qwen"]
    assert await list_models(client, kind="embed") == ["bge-m3"]


async def test_an_embedding_comes_back_as_a_list_of_numbers():
    """Встраивание достаётся из ответа списком чисел."""
    client = provider({
        EMBEDDINGS: httpx.Response(200, json={"data": [{"embedding": [0.1, 0.2]}]}),
    })
    assert await embed(client, "bge-m3", "привет") == [0.1, 0.2]


async def test_an_empty_embedding_response_fails_loudly():
    """Пустой ответ на встраивание — ошибка, а не пустой список."""
    client = provider({EMBEDDINGS: httpx.Response(200, json={"data": []})})
    with pytest.raises(RuntimeError, match="empty data"):
        await embed(client, "bge-m3", "привет")


async def test_an_embedding_without_numbers_fails_loudly():
    """Ответ без самого вектора — тоже ошибка."""
    client = provider({
        EMBEDDINGS: httpx.Response(200, json={"data": [{"embedding": None}]}),
    })
    with pytest.raises(RuntimeError, match="missing/invalid embedding"):
        await embed(client, "bge-m3", "привет")


async def test_embed_raises_when_the_provider_answers_with_an_error():
    """Провайдер ответил ошибкой на встраивание — исключение, а не тихий сбой."""
    client = provider({EMBEDDINGS: httpx.Response(500, text="сломалось")})
    with pytest.raises(httpx.HTTPStatusError):
        await embed(client, "bge-m3", "привет")


@pytest.mark.parametrize(
    ("check", "routes"),
    [
        pytest.param(check_chat, {}, id="чат, список моделей"),
        pytest.param(
            check_chat,
            {MODELS: models_response("qwen"), CHAT: httpx.ConnectError("оборвалось")},
            id="чат, пробный запрос",
        ),
        pytest.param(check_embed, {}, id="векторы, список моделей"),
        pytest.param(
            check_embed,
            {
                MODELS: models_response("bge-m3"),
                EMBEDDINGS: httpx.ConnectError("оборвалось"),
            },
            id="векторы, пробный запрос",
        ),
    ],
)
async def test_a_failed_check_leaves_a_trace_in_the_log(check, routes, caplog):
    """Неудачная проверка оставляет трассировку в журнале.

    Наружу уходит короткое «род и текст» — этого хватает подсказке в окне,
    но не хватает, чтобы понять, где именно оборвалось. Трассировка нужна
    там, где её потом читают: в журнале.
    """
    model = "qwen" if check is check_chat else "bge-m3"

    with caplog.at_level("ERROR", logger="adapters.lm_studio"):
        passed, _ = await check(provider(routes), model)

    assert passed is False
    # Смотрим записи именно адаптера: по всему журналу трассировку мог бы
    # оставить кто угодно, и сторож позеленел бы на чужой.
    assert any(
        rec.exc_info for rec in caplog.records if rec.name == "adapters.lm_studio"
    )
