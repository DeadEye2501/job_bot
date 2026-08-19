"""Следствия перечня моделей у провайдера и проверки, что модель отвечает.

Проверка настоящая, а не по списку: модель может числиться у провайдера и не
отвечать — из-за нехватки памяти, чужой занятости или несовместимости с родом
обращения. Род провайдеры отдают не всегда, и тогда его угадывают по имени.
"""

import logging

import httpx
import pytest

from adapters.lm_models import check_model, list_models
from tests.fakes.llm import (
    CHAT,
    EMBEDDINGS,
    MODELS,
    models_response,
    provider,
)

# Своё, потому что зовущий один: путь родной для LM Studio, и спрашивают его
# только проверки отбора загруженных моделей. Общие пары лежат у подделки —
# они нужны и её собственным проверкам.
NATIVE_MODELS = ("GET", "/api/v0/models")
async def test_a_loaded_chat_model_passes_the_check():
    """Модель есть в списке и отвечает на пинг — проверка пройдена."""
    client = provider({
        MODELS: models_response("qwen", "llama"),
        CHAT: httpx.Response(200, json={"choices": []}),
    })
    assert await check_model(client, "qwen", "chat") == (True, "qwen")
async def test_a_missing_chat_model_fails_the_check_and_lists_what_there_is():
    """Если модели нет, отказ называет, что у провайдера есть."""
    client = provider({MODELS: models_response("llama", "mistral")})
    passed, message = await check_model(client, "qwen", "chat")
    assert passed is False
    assert "llama" in message and "mistral" in message


async def test_a_provider_with_no_models_says_so_plainly():
    """Пустой список моделей называется словами, а не пустой строкой."""
    client = provider({MODELS: models_response()})
    passed, message = await check_model(client, "qwen", "chat")
    assert passed is False
    assert "no models loaded" in message


async def test_a_chat_model_that_fails_the_ping_does_not_pass():
    """Модель в списке есть, но пинг не прошёл — проверка не пройдена."""
    client = provider({
        MODELS: models_response("qwen"),
        CHAT: httpx.Response(500, text="сломалось"),
    })
    passed, message = await check_model(client, "qwen", "chat")
    assert passed is False
    assert "500" in message


async def test_a_provider_error_response_names_its_kind_and_code():
    """Провайдер ответил ошибкой на список моделей — сообщение называет её род и код."""
    client = provider({})
    passed, message = await check_model(client, "qwen", "chat")
    assert passed is False
    assert "HTTPStatusError" in message
    assert "599" in message


async def test_a_loaded_embedding_model_passes_the_check():
    """Модель встраиваний есть и отвечает — проверка пройдена."""
    client = provider({
        MODELS: models_response("bge-m3"),
        EMBEDDINGS: httpx.Response(200, json={"data": [{"embedding": [0.1]}]}),
    })
    assert await check_model(client, "bge-m3", "embed") == (True, "bge-m3")
async def test_a_missing_embedding_model_is_told_what_there_is_too():
    """Отсутствующая модель встраиваний проверку не проходит, и отказ называет,
    что у провайдера есть.

    Оба рода моделей выбираются на одном экране настроек, и опечатку человек
    сверяет по перечню. Без перечня у одного из двух сверять нечем.
    """
    client = provider({MODELS: models_response("qwen", "llama")})
    passed, message = await check_model(client, "bge-m3", "embed")
    assert passed is False
    assert "qwen" in message and "llama" in message


async def test_an_embedding_model_that_fails_the_ping_does_not_pass():
    """Модель встраиваний в списке есть, но пинг не прошёл — проверка не пройдена."""
    client = provider({
        MODELS: models_response("bge-m3"),
        EMBEDDINGS: httpx.Response(500, text="сломалось"),
    })
    passed, message = await check_model(client, "bge-m3", "embed")
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


async def test_a_broken_native_endpoint_leaves_its_trace_in_the_log(caplog):
    """Отказ родного пути оставляет в журнале трассировку.

    Запасной путь работает, и снаружи разницы не видно — кроме того, что род
    модели угадывается по имени, а не берётся у провайдера. Разбирать, почему
    выбор моделей стал врать, придётся по журналу.
    """
    client = provider({
        NATIVE_MODELS: httpx.Response(200, text="not json"),
        MODELS: models_response("qwen"),
    })

    with caplog.at_level(logging.DEBUG, logger="adapters.lm_models"):
        await list_models(client, kind="chat")

    # Смотрим записи именно адаптера: по всему журналу трассировку мог бы
    # оставить кто угодно, и сторож позеленел бы на чужой.
    assert any(
        rec.exc_info for rec in caplog.records if rec.name == "adapters.lm_models"
    )
async def test_nothing_loaded_is_not_the_same_as_no_native_path():
    """Родной путь ответил пустотой — выгруженные модели наверх не идут.

    Пустой ответ родного пути значит «этого рода не загружено ничего», а не
    «пути нет». Спроси после него общий список — и в выбор вернутся ровно те
    выгруженные модели, ради которых родной путь и заведён: выбравший такую
    ждёт полминуты подкачки.
    """
    client = provider({
        NATIVE_MODELS: httpx.Response(200, json={"data": []}),
        MODELS: models_response("qwen"),
    })

    assert await list_models(client, kind="chat") == []


@pytest.mark.parametrize(
    ("kind", "model", "routes"),
    [
        pytest.param("chat", "qwen", {}, id="чат, список моделей"),
        pytest.param(
            "chat",
            "qwen",
            {MODELS: models_response("qwen"), CHAT: httpx.ConnectError("оборвалось")},
            id="чат, пробный запрос",
        ),
        pytest.param("embed", "bge-m3", {}, id="векторы, список моделей"),
        pytest.param(
            "embed",
            "bge-m3",
            {
                MODELS: models_response("bge-m3"),
                EMBEDDINGS: httpx.ConnectError("оборвалось"),
            },
            id="векторы, пробный запрос",
        ),
    ],
)
async def test_a_failed_check_leaves_a_trace_in_the_log(kind, model, routes, caplog):
    """Неудачная проверка оставляет трассировку в журнале.

    Наружу уходит короткое «род и текст» — этого хватает подсказке в окне,
    но не хватает, чтобы понять, где именно оборвалось. Трассировка нужна
    там, где её потом читают: в журнале.
    """
    with caplog.at_level("ERROR", logger="adapters.lm_models"):
        passed, _ = await check_model(provider(routes), model, kind)

    assert passed is False
    # Смотрим записи именно адаптера: по всему журналу трассировку мог бы
    # оставить кто угодно, и сторож позеленел бы на чужой.
    assert any(
        rec.exc_info for rec in caplog.records if rec.name == "adapters.lm_models"
    )
