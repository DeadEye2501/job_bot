"""Проверяющий запасного пути: убедительно ли обоснование, по каждому пункту раскладки.

Проверка открывается наружу при любой беде провайдера, как сверка писем:
заполнение из-за сбоя проверки не стоит.
"""

import pytest

from backend.llm.fill_review import Verdict, review_fallbacks
from backend.payloads import FieldEntry
from tests.fakes.agent import layout_item
from tests.fakes.llm import CHAT, chat_json, data_block, provider, provider_trouble

INVENTORY = [
    FieldEntry("#about", "О себе", "textarea", False, []),
    FieldEntry("#skills", "Умения мастера", "text", False, []),
]

ITEMS = [layout_item("#about", "Навыки: шитьё, раскрой", "на странице нет поля навыков")]


async def test_each_item_gets_its_own_verdict_with_reason_and_field():
    client = provider({CHAT: chat_json({"verdicts": [
        {"selector": "#about", "ok": False, "reason": "есть поле «Навыки»", "field": "#skills"},
    ]})})

    verdicts = await review_fallbacks(client, "qwen", INVENTORY, ITEMS)

    assert verdicts == {"#about": Verdict(False, "есть поле «Навыки»", "#skills")}


async def test_a_convincing_reason_is_let_through():
    client = provider({CHAT: chat_json({"verdicts": [
        {"selector": "#about", "ok": True, "reason": "", "field": None},
    ]})})

    verdicts = await review_fallbacks(client, "qwen", INVENTORY, ITEMS)

    assert verdicts["#about"].ok is True


async def test_the_inventory_and_the_reasons_reach_the_model_as_data():
    client = provider({CHAT: chat_json({"verdicts": []})})

    await review_fallbacks(client, "qwen", INVENTORY, ITEMS)

    body = data_block(client.sent[0])
    assert "Умения мастера" in body and "на странице нет поля навыков" in body


@pytest.mark.parametrize("trouble", provider_trouble(
    pytest.param(chat_json({"verdicts": "непонятно"}), id="verdicts not a list"),
))
async def test_any_trouble_lets_every_fallback_through_and_says_so(trouble, caplog):
    client = provider({CHAT: trouble})

    verdicts = await review_fallbacks(client, "qwen", INVENTORY, ITEMS)

    assert verdicts == {"#about": Verdict(True, "", None)}
    assert any("проверка запасного пути" in record.getMessage() for record in caplog.records)
