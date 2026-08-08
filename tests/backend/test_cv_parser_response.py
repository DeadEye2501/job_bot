"""Следствия, которые наблюдает внешний слой `parse_cv`.

Разбор самого JSON проверяется отдельно; здесь — что уходит в запросе и что
происходит, когда провайдер отвечает не так, как надо.
"""

import json

import httpx

from backend.cv_parser import parse_cv
from tests.fakes.llm import CHAT, chat_response, provider


MINIMAL_CV = (
    '{"profile": {"first_name": "Алексей", "last_name": "Фролов",'
    ' "title": "Python-разработчик", "email": "a@b.c"}}'
)


async def test_an_empty_text_never_reaches_the_provider():
    """Пустой текст резюме до провайдера не доходит."""
    client = provider({})

    assert await parse_cv("", client, "qwen") is None
    assert client.sent == []


async def test_a_whitespace_only_text_never_reaches_the_provider():
    """Текст из одних пробелов тоже не доходит."""
    client = provider({})

    assert await parse_cv("   \n\t  ", client, "qwen") is None
    assert client.sent == []


async def test_a_long_resume_is_cut_before_sending():
    """Длинное резюме урезается до отправки: часть опыта теряется молча."""
    client = provider({CHAT: chat_response(MINIMAL_CV)})

    await parse_cv("я" * 30000, client, "qwen")

    # Считаем в самом резюме, а не во всём теле: указание модели тоже
    # по-русски и своих «я» содержит достаточно, чтобы счёт стал бессмысленным.
    payload = json.loads(client.sent[0].read())
    assert len(payload["messages"][1]["content"]) == 20000


async def test_the_prompt_and_the_resume_go_as_separate_messages():
    """Указание модели и текст резюме уходят разными сообщениями."""
    client = provider({CHAT: chat_response(MINIMAL_CV)})

    await parse_cv("моё резюме", client, "qwen")

    payload = json.loads(client.sent[0].read())
    roles = [m["role"] for m in payload["messages"]]
    assert roles == ["system", "user"]
    assert payload["messages"][1]["content"] == "моё резюме"
    assert payload["model"] == "qwen"


async def test_a_provider_error_yields_no_parse():
    """Отказ провайдера не роняет вызывающего, а даёт отсутствие разбора."""
    client = provider({CHAT: httpx.Response(500, text="сломалось")})

    assert await parse_cv("резюме", client, "qwen") is None


async def test_a_broken_connection_yields_no_parse():
    """Оборванная связь тоже даёт отсутствие разбора, а не исключение."""
    client = provider({CHAT: httpx.ConnectError("сеть недоступна")})

    assert await parse_cv("резюме", client, "qwen") is None


async def test_a_response_without_choices_yields_no_parse():
    """Ответ без вариантов — не разбор."""
    client = provider({CHAT: httpx.Response(200, json={})})

    assert await parse_cv("резюме", client, "qwen") is None


async def test_a_response_with_an_empty_choice_list_yields_no_parse():
    """Пустой список вариантов — тоже не разбор."""
    client = provider({CHAT: httpx.Response(200, json={"choices": []})})

    assert await parse_cv("резюме", client, "qwen") is None


async def test_a_choice_without_a_message_yields_no_parse():
    """Вариант без сообщения — не разбор."""
    client = provider({CHAT: httpx.Response(200, json={"choices": [{}]})})

    assert await parse_cv("резюме", client, "qwen") is None


async def test_an_answer_that_is_not_json_yields_no_parse():
    """Модель ответила словами вместо JSON — разбора нет."""
    client = provider({CHAT: chat_response("извините, я языковая модель")})

    assert await parse_cv("резюме", client, "qwen") is None


async def test_a_body_that_is_not_json_at_all_yields_no_parse():
    """Провайдер ответил двухсоткой, но тело — не JSON: разбора нет."""
    client = provider({CHAT: httpx.Response(200, text="не json")})

    assert await parse_cv("резюме", client, "qwen") is None


async def test_a_truncated_answer_still_parses_what_it_can():
    """Упёршийся в предел ответ разбирается, если JSON в нём всё же целый."""
    client = provider({CHAT: chat_response(MINIMAL_CV, finish_reason="length")})

    parsed = await parse_cv("резюме", client, "qwen")

    assert parsed is not None
    assert parsed.profile.first_name == "Алексей"


async def test_a_well_formed_answer_becomes_a_parsed_resume():
    """Годный ответ превращается в разобранное резюме."""
    client = provider({CHAT: chat_response(MINIMAL_CV)})

    parsed = await parse_cv("резюме", client, "qwen")

    assert parsed is not None
    assert parsed.profile.email == "a@b.c"
    assert parsed.languages == []
    assert parsed.skills == []
    assert parsed.experience == []
