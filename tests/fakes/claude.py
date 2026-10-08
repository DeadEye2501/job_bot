"""Подделка API Anthropic: настоящий клиент SDK поверх подставного транспорта.

Устроена как `tests/fakes/llm.provider`, и правила у неё те же: незаданный
путь отвечает 599 со своим именем, исключение бросается, список отвечает по
очереди. Отдельной подделкой, а не той же: SDK ходит через `httpx2`, и
транспорт с ответами у него свои.
"""

import httpx2
from anthropic import DefaultAsyncHttpxClient

from adapters.claude import ClaudeClient
from tests.fakes.llm import handler

MESSAGES = ("POST", "/v1/messages")
MODELS = ("GET", "/v1/models")


def claude(routes: dict, *, api_key: str = "sk-test") -> ClaudeClient:
    """Клиент к поддельному Anthropic; ушедшие запросы копятся в `client.sent`."""
    sent: list[httpx2.Request] = []
    transport = httpx2.MockTransport(handler(routes, sent, httpx2))
    client = ClaudeClient(
        api_key=api_key,
        base_url="https://api.anthropic.com",
        max_retries=0,
        http_client=DefaultAsyncHttpxClient(transport=transport),
    )
    client.sent = sent
    return client


def _reply(content: list, stop_reason: str, **extra) -> httpx2.Response:
    """Ответ `/v1/messages` в форме Anthropic с заданными блоками и причиной конца."""
    return httpx2.Response(200, json={
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "claude-sonnet-5-5",
        "content": content,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": 1, "output_tokens": 1},
        **extra,
    })


def message(text: str, *, stop_reason: str = "end_turn") -> httpx2.Response:
    """Ответ модели: блок размышления и блок текста, как отвечает Sonnet."""
    return _reply(
        [
            {"type": "thinking", "thinking": "размышление модели", "signature": "sig"},
            {"type": "text", "text": text},
        ],
        stop_reason,
    )


def refusal(category: str = "cyber") -> httpx2.Response:
    """Отказ модели отвечать: код 200, причина в `stop_details`."""
    return _reply(
        [],
        "refusal",
        stop_details={"type": "refusal", "category": category, "explanation": "нет"},
    )


def model_list(*ids: str) -> httpx2.Response:
    """Ответ `/v1/models` в форме Anthropic."""
    return httpx2.Response(200, json={
        "data": [
            {
                "type": "model",
                "id": one,
                "display_name": one,
                "created_at": "2026-01-01T00:00:00Z",
            }
            for one in ids
        ],
        "has_more": False,
        "first_id": ids[0] if ids else None,
        "last_id": ids[-1] if ids else None,
    })
