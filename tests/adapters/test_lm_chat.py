"""Следствия разговора с чат-моделью: что уходит и что получается.

Подделан транспорт, а не клиент: пути, тело запроса и разбор ответа остаются
настоящими. Отдельный предмет здесь — отказы: у ответа без содержимого, у
ответа чужой формы и у ответа, упёршегося в предел токенов, разные метки, и
по ним зовущий выбирает свой откат.
"""

import logging

import httpx
import pytest

from adapters.lm_chat import ChatRequest, chat
from tests.fakes.llm import CHAT, chat_response, provider


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
