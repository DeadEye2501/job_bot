"""Следствия, которые наблюдают тесты `adapters/lm_studio.py`.

Модуль — тонкая прослойка к любому провайдеру, совместимому с OpenAI. Его
работа целиком состоит из того, что уходит в запросе и что получается из
ответа, поэтому подделан транспорт, а не клиент: заголовки, пути и разбор
JSON остаются настоящими.
"""

import logging

import httpx
import pytest

from adapters.lm_studio import (
    ChatRequest,
    chat,
    check_chat,
    check_embed,
    embed,
    list_models,
    make_client,
)
from backend.runtime_settings import LlmProviderConfig
from tests.fakes.llm import (
    CHAT,
    EMBEDDINGS,
    MODELS,
    chat_response,
    models_response,
    provider,
)

# Своё, потому что зовущий один: путь родной для LM Studio, и спрашивают его
# только проверки отбора загруженных моделей. Общие пары лежат у подделки —
# они нужны и её собственным проверкам.
NATIVE_MODELS = ("GET", "/api/v0/models")


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


async def test_a_missing_embedding_model_is_told_what_there_is_too():
    """Отсутствующая модель встраиваний проверку не проходит, и отказ называет,
    что у провайдера есть.

    Оба рода моделей выбираются на одном экране настроек, и опечатку человек
    сверяет по перечню. Без перечня у одного из двух сверять нечем.
    """
    client = provider({MODELS: models_response("qwen", "llama")})
    passed, message = await check_embed(client, "bge-m3")
    assert passed is False
    assert "qwen" in message and "llama" in message


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

    with caplog.at_level(logging.DEBUG, logger="adapters.lm_studio"):
        await list_models(client, kind="chat")

    # Смотрим записи именно адаптера: по всему журналу трассировку мог бы
    # оставить кто угодно, и сторож позеленел бы на чужой.
    assert any(
        rec.exc_info for rec in caplog.records if rec.name == "adapters.lm_studio"
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


async def test_a_request_with_its_own_deadline_carries_it_to_the_provider():
    """Своё время ожидания доезжает до провайдера.

    Оно заведено там, где обращение заведомо длиннее прочих: разбор
    резюме на слабой локальной модели идёт минутами. Не доехав, такой
    запрос обрывался бы по общему сроку клиента, и длинная работа не
    заканчивалась бы никогда.
    """
    client = provider({CHAT: chat_response("готово")})

    await chat(
        client,
        "qwen",
        ChatRequest(purpose="разбор резюме", messages=[], max_tokens=8, timeout=300.0),
        logging.getLogger(__name__),
    )

    assert client.sent[0].extensions["timeout"]["read"] == 300.0


async def test_an_answer_cut_by_the_token_limit_names_its_purpose(caplog):
    """Упёршееся в предел обращение оставляет в журнале своё имя.

    Обрыв по пределу — не отказ: обрезанный ответ иногда разбирается, и
    решает это зовущий. Но разбирать потом, почему разбор соврал, придётся по
    журналу, а обращений к модели семеро — без имени строка не скажет,
    которое из них не доехало.
    """
    client = provider({CHAT: chat_response('{"a":', finish_reason="length")})
    log = logging.getLogger("tests.token_limit")

    with caplog.at_level(logging.WARNING, logger="tests.token_limit"):
        answer = await chat(
            client,
            "qwen",
            ChatRequest(purpose="разбор вакансии", messages=[], max_tokens=8),
            log,
        )

    assert answer.text == '{"a":'
    assert [
        rec.getMessage()
        for rec in caplog.records
        if rec.name == "tests.token_limit"
    ] == [
        "разбор вакансии: модель упёрлась в предел токенов, ответ может быть обрезан"
    ]


@pytest.mark.parametrize(
    "content",
    [
        pytest.param(None, id="null вместо содержимого"),
        pytest.param([], id="содержимое блоками"),
        pytest.param("   ", id="одни пробелы"),
    ],
)
async def test_an_answer_without_content_becomes_a_refusal_that_names_itself(
    caplog, content
):
    """Ответ без содержимого становится отказом и оставляет в журнале имя.

    Форма ответа при этом правильная — модель просто не сказала ничего, и
    говорит она это тремя способами: `null`, пустым списком блоков (так
    отвечают провайдеры, совместимые с OpenAI наполовину) и пустой строкой.
    Последняя ходовее прочих: так отвечает рассуждающая модель, потратившая
    весь предел токенов на размышление.

    Зовущему это обязано достаться отказом, а не пустым текстом. Пустоту он
    разбирать не умеет: у `null` и списка `.strip()` даёт исключение, а
    пустая строка тихо доезжает до приговора и читается как «в посте ничего
    нет» — то есть отказ провайдера превращается в приговор объявлению, и
    живая вакансия уходит в мусор. Разбирать потом, кто именно остался без
    ответа, придётся по журналу, где обращений семеро.
    """
    client = provider({CHAT: chat_response(content)})
    log = logging.getLogger("tests.empty_content")

    with caplog.at_level(logging.WARNING, logger="tests.empty_content"):
        answer = await chat(
            client,
            "qwen",
            ChatRequest(purpose="разбор ответа HR", messages=[], max_tokens=8),
            log,
        )

    assert answer.text is None
    assert answer.error == "empty_content"
    assert [
        rec.getMessage()
        for rec in caplog.records
        if rec.name == "tests.empty_content"
    ] == ["разбор ответа HR: провайдер ответил без содержимого"]


async def test_an_empty_answer_that_hit_the_token_limit_names_the_limit_too(caplog):
    """Пустой ответ, упёршийся в предел токенов, называет и предел.

    Так отвечает модель, потратившая весь предел на размышление: содержимого
    нет, а причина этому — упёршийся предел. Одной записи мало: она называет
    симптом и молчит о причине, тогда как поднять предел — единственное, что
    по этой беде вообще можно сделать.
    """
    client = provider({CHAT: chat_response(None, finish_reason="length")})
    log = logging.getLogger("tests.empty_at_the_limit")

    with caplog.at_level(logging.WARNING, logger="tests.empty_at_the_limit"):
        answer = await chat(
            client,
            "qwen",
            ChatRequest(purpose="разбор вакансии", messages=[], max_tokens=8),
            log,
        )

    assert answer.error == "empty_content"
    assert [
        rec.getMessage()
        for rec in caplog.records
        if rec.name == "tests.empty_at_the_limit"
    ] == [
        "разбор вакансии: модель упёрлась в предел токенов, ответ может быть обрезан",
        "разбор вакансии: провайдер ответил без содержимого",
    ]


async def test_an_answer_without_a_message_at_all_is_malformed_not_empty():
    """Ответ без самого сообщения — неразбираемый, а не пустой.

    `"message": null` присылают провайдеры, совместимые с OpenAI наполовину.
    Отличать его от пустого содержимого стоит: пустое содержимое — ответ
    правильной формы, а здесь сломан конверт, и метка отказа ведёт разбор
    беды в другую сторону. До правки такой ответ уходил зовущему
    исключением, мимо его ловушки.
    """
    client = provider(
        {CHAT: httpx.Response(200, json={"choices": [{"message": None}]})}
    )

    answer = await chat(
        client,
        "qwen",
        ChatRequest(purpose="разбор вакансии", messages=[], max_tokens=8),
        logging.getLogger(__name__),
    )

    assert answer.text is None
    assert answer.error.startswith("malformed_response")
