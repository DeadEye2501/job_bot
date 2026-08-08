"""Когда чат и векторы делят одно соединение с языковой моделью.

Соединение заводится на адрес и ключ, а модель задаётся в каждом запросе.
Поэтому две настройки, совпавшие адресом и ключом, обслуживает один клиент —
разводить их из-за разных моделей значило бы держать вдвое больше соединений
без всякой причины.
"""

import pytest

from backend.bot.client import _shares_provider
from backend.runtime_settings import LlmProviderConfig


def _provider(base_url="http://a", api_key="ключ", model="qwen"):
    """Настройка провайдера в том виде, в каком её сравнивают."""
    return LlmProviderConfig(base_url=base_url, api_key=api_key, model=model)


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        pytest.param(_provider(), _provider(), True, id="совпадают"),
        pytest.param(
            _provider(), _provider(base_url="http://b"), False, id="разные адреса"
        ),
        pytest.param(
            _provider(), _provider(api_key="другой"), False, id="разные ключи"
        ),
        pytest.param(
            _provider(model="qwen"),
            _provider(model="llama"),
            True,
            id="разные модели — всё равно один",
        ),
        pytest.param(None, _provider(), False, id="первой нет"),
        pytest.param(_provider(), None, False, id="второй нет"),
        pytest.param(None, None, False, id="нет обеих"),
    ],
)
def test_two_providers_share_a_client_when_the_endpoint_and_key_match(a, b, expected):
    """Две настройки делят одно соединение, если совпали адрес и ключ.

    Модель не сравнивается нарочно: она задаётся на каждый запрос, а не на
    соединение.
    """
    assert _shares_provider(a, b) is expected
