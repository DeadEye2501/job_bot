"""Следствия второй проверки письма — сверки фактов с профилем.

Проверка открывается наружу при любой беде: сеть отвалилась, ответ пришёл не
той формы, вердикт незнакомый — письмо считается годным. Иначе временный сбой
провайдера превращался бы в отказ отправлять отклики вовсе, а первый проход
уже усилен запретами на выдумывание.
"""

import httpx
import pytest

from backend.llm.factcheck import factcheck_cover_letter
from tests.fakes.llm import CHAT, chat_json, chat_response, provider


def _verdict(verdict, issues=None) -> httpx.Response:
    """Ответ проверки в её обычной форме."""
    return chat_json({"verdict": verdict, "issues": issues})


async def test_a_clean_verdict_lets_the_letter_through():
    """Чистый вердикт письмо пропускает и замечаний не приносит."""
    client = provider({CHAT: _verdict("ok", ["это замечание не нужно"])})

    ok, issues = await factcheck_cover_letter("профиль", "письмо", client, "qwen")

    assert ok is True
    assert issues == []


async def test_a_rejecting_verdict_stops_the_letter_and_names_why():
    """Отклоняющий вердикт письмо останавливает и называет причины."""
    client = provider(
        {CHAT: _verdict("reject", ["выдумал Kubernetes", "перепутал компании"])}
    )

    ok, issues = await factcheck_cover_letter("профиль", "письмо", client, "qwen")

    assert ok is False
    assert issues == ["выдумал Kubernetes", "перепутал компании"]


async def test_no_more_than_three_reasons_are_kept():
    """Замечаний берётся не больше трёх: остальное в интерфейс не помещается."""
    client = provider({CHAT: _verdict("reject", ["раз", "два", "три", "четыре"])})

    _, issues = await factcheck_cover_letter("профиль", "письмо", client, "qwen")

    assert issues == ["раз", "два", "три"]


async def test_junk_among_the_reasons_is_skipped():
    """Не-строки среди замечаний пропускаются, а не роняют разбор."""
    client = provider({CHAT: _verdict("reject", [42, None, "настоящее замечание"])})

    _, issues = await factcheck_cover_letter("профиль", "письмо", client, "qwen")

    assert issues == ["настоящее замечание"]


async def test_a_verdict_wrapped_in_a_code_fence_is_still_read():
    """Вердикт, обёрнутый в разметку кода, всё равно читается.

    Модель охотно оборачивает ответ тройными кавычками, хотя её об этом не
    просили.
    """
    client = provider(
        {CHAT: chat_response('```json\n{"verdict": "reject", "issues": []}\n```')}
    )

    ok, _ = await factcheck_cover_letter("профиль", "письмо", client, "qwen")

    assert ok is False


@pytest.mark.parametrize(
    "prepared",
    [
        pytest.param(httpx.Response(500, text="упал"), id="отказ провайдера"),
        pytest.param(httpx.ConnectError("сеть отвалилась"), id="обрыв связи"),
        pytest.param(httpx.Response(200, json={"нет": "выборов"}), id="чужая форма"),
        pytest.param(chat_response("совсем не json"), id="не разбирается"),
        pytest.param(chat_response('["список"]'), id="список вместо объекта"),
        pytest.param(chat_response('{"verdict": "может быть"}'), id="чужой вердикт"),
        pytest.param(chat_response("{}"), id="вердикта нет"),
    ],
)
async def test_any_trouble_lets_the_letter_through(prepared):
    """Любая беда с проверкой письмо пропускает, а не задерживает.

    Второй проход — страховка поверх первого, и превращать его сбой в
    отказ отправлять отклики было бы хуже, чем изредка пропустить
    непроверенное письмо.
    """
    client = provider({CHAT: prepared})

    ok, issues = await factcheck_cover_letter("профиль", "письмо", client, "qwen")

    assert ok is True
    assert issues == []
