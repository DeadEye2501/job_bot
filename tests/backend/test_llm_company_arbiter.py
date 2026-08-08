"""Следствия обращения к модели как к арбитру при сведении компаний.

Арбитр отвечает номером одной из показанных ему записей или отказом. Любая
беда — сеть, чужая форма ответа, номер не числом — вырождается в отказ: тогда
заведётся новая запись, и это поправимо, а склеивание двух разных компаний
необратимо на уровне вакансий.

Причина решения возвращается наружу отдельной строкой и попадает в журнал:
без неё по записи не разобрать, чем всё кончилось.
"""

import httpx
import pytest

from backend.llm import dedupe_company_with_llm
from tests.fakes.llm import CHAT, chat_json, chat_response, messages_of, provider


class _Candidate:
    """Запись компании в том виде, в каком её показывают арбитру."""

    def __init__(self, id, name, aliases=None, website=None):
        self.id = id
        self.name = name
        self.aliases = aliases
        self.website = website


def _answer(matched_id=None, reasoning=None) -> httpx.Response:
    """Ответ арбитра в его обычной форме."""
    return chat_json({"matched_id": matched_id, "reasoning": reasoning})


async def _ask(client, candidates, name="Сбербанк Тех"):
    """Спросить арбитра о названии при заданных кандидатах."""
    return await dedupe_company_with_llm(
        client,
        "qwen",
        parsed_name=name,
        parsed_website=None,
        candidates=candidates,
    )


async def test_without_candidates_nothing_is_asked():
    """Без кандидатов арбитра не беспокоят вовсе."""
    client = provider({})

    matched, reasoning = await _ask(client, [])

    assert matched is None
    assert reasoning == "no_candidates"
    assert client.sent == []


async def test_a_named_candidate_comes_back_with_the_reason():
    """Названный арбитром номер возвращается вместе с причиной."""
    client = provider({CHAT: _answer(7, "это одна и та же компания")})

    matched, reasoning = await _ask(client, [_Candidate(7, "Сбербанк")])

    assert matched == 7
    assert reasoning == "это одна и та же компания"


async def test_a_refusal_comes_back_with_the_reason():
    """Отказ арбитра возвращается вместе с причиной."""
    client = provider({CHAT: _answer(None, "разные конторы")})

    matched, reasoning = await _ask(client, [_Candidate(7, "Сбербанк")])

    assert matched is None
    assert reasoning == "разные конторы"


async def test_a_number_given_as_text_is_still_read():
    """Номер, присланный строкой, всё равно читается числом.

    Модели свойственно возвращать «7» в кавычках, и отказываться от такого
    ответа значило бы заводить лишнюю запись на пустом месте.
    """
    client = provider({CHAT: _answer("7", "та же")})

    matched, _ = await _ask(client, [_Candidate(7, "Сбербанк")])

    assert matched == 7


async def test_a_number_that_is_not_a_number_is_refused_with_a_named_reason():
    """Номер, который числом не назвать, приводит к отказу с внятной причиной."""
    client = provider({CHAT: _answer("седьмой", "та же")})

    matched, reasoning = await _ask(client, [_Candidate(7, "Сбербанк")])

    assert matched is None
    assert "invalid_id" in reasoning


async def test_an_answer_wrapped_in_a_code_fence_is_still_read():
    """Ответ, обёрнутый в разметку кода, всё равно читается."""
    client = provider(
        {CHAT: chat_response('```json\n{"matched_id": 7, "reasoning": "та же"}\n```')}
    )

    matched, _ = await _ask(client, [_Candidate(7, "Сбербанк")])

    assert matched == 7


async def test_the_candidates_are_shown_with_all_they_have():
    """Кандидаты показываются арбитру с номером, именем, написаниями и сайтом."""
    client = provider({CHAT: _answer(None, "нет")})

    await _ask(
        client,
        [
            _Candidate(7, "Сбербанк", ["Sber"], "https://sber.ru"),
            _Candidate(8, "Ромашка"),
        ],
    )

    prompt = messages_of(client.sent[0])["system"]
    assert 'id=7, name="Сбербанк", aliases=[Sber], website="https://sber.ru"' in prompt
    assert 'id=8, name="Ромашка", aliases=[—], website="—"' in prompt


@pytest.mark.parametrize(
    ("prepared", "marker"),
    [
        pytest.param(
            httpx.Response(500, text="упал"), "llm_http_error", id="отказ провайдера"
        ),
        pytest.param(
            httpx.ConnectError("сеть отвалилась"),
            "llm_request_error",
            id="обрыв связи",
        ),
        pytest.param(
            httpx.Response(200, json={"нет": "выборов"}),
            "malformed_response",
            id="чужая форма",
        ),
        pytest.param(
            chat_response("совсем не json"), "unparseable_json", id="не разбирается"
        ),
    ],
)
async def test_any_trouble_becomes_a_refusal_that_names_itself(prepared, marker):
    """Любая беда становится отказом, и причина называет, какая именно.

    Отказ безопаснее склеивания: заведётся лишняя запись, и её можно слить
    руками, а неверное склеивание необратимо.
    """
    client = provider({CHAT: prepared})

    matched, reasoning = await _ask(client, [_Candidate(7, "Сбербанк")])

    assert matched is None
    assert marker in reasoning


async def test_an_answer_that_is_not_an_object_becomes_a_refusal():
    """Ответ не объектом становится отказом, а не падением."""
    client = provider({CHAT: chat_response("[7]")})

    matched, reasoning = await _ask(client, [_Candidate(7, "Сбербанк")])

    assert matched is None
    assert reasoning == ""
