"""Следствия соединения с провайдером моделей.

Подделан транспорт, а не клиент: заголовок с ключом, адрес и срок ожидания
остаются настоящими — из них соединение и состоит.
"""

from adapters.lm_studio import make_client
from backend.provider_config import LlmProviderConfig


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
