"""Поставщик модели в настройках: из каких полей он состоит и когда настроен.

Своим модулем, а не внутри `runtime_settings`: правило годности строки
спрашивают подъём настроек из базы, мост окна и выбор клиента в адаптерах, и
ни одному из них не нужен кеш настроек целиком.
"""

from dataclasses import dataclass, field
from urllib.parse import urlsplit

MODEL_FILE_SUFFIX = ".gguf"

CLAUDE_HOST = "api.anthropic.com"

# Служебный адрес вместо настоящего: Claude Code ходит под входом человека по
# подписке, и адреса сервера у такого поставщика нет.
CLAUDE_CODE_ADDRESS = "claude-code"


def names_model_file(base_url: str | None, model: str | None) -> bool:
    """Строка поставщика указывает не на сервер, а на файл модели на диске.

    Адреса у такой строки нет, а в поле модели — путь к GGUF.
    """
    return not base_url and bool(model) and model.lower().endswith(MODEL_FILE_SUFFIX)


def serves_claude(base_url: str | None) -> bool:
    """Адрес ведёт к API Anthropic."""
    return urlsplit(base_url or "").hostname == CLAUDE_HOST


def serves_claude_code(base_url: str | None) -> bool:
    """Адрес — служебное слово Claude Code."""
    return (base_url or "").strip() == CLAUDE_CODE_ADDRESS


def chat_only(base_url: str | None) -> bool:
    """Поставщик говорит, но векторов не считает: Claude по API и через Claude Code."""
    return serves_claude(base_url) or serves_claude_code(base_url)


def serves_kind(kind: str, base_url: str | None) -> bool:
    """Может ли поставщик по этому адресу служить роду `kind` ('chat' | 'embed')."""
    return not (kind == "embed" and chat_only(base_url))


def provider_complete(kind: str, base_url: str | None, model: str | None) -> bool:
    """Годится ли строка в поставщика рода `kind` ('chat' | 'embed').

    Модель названа, и есть, где её взять: адрес сервера, а у эмбеддингов ещё
    и файл модели на диске. Чат из файла не говорит, а Claude — ни по API, ни
    через Claude Code — не считает эмбеддингов: такого клиента бот собрал бы и
    падал бы на каждом обращении, а у эмбеддингов ещё и терял бы посты. Правило
    одно на подъём из базы и на окно: разъедься они, строка, принятая окном, не
    поднималась бы ботом.
    """
    if not model or not serves_kind(kind, base_url):
        return False
    if kind != "embed":
        return bool(base_url)
    return bool(base_url) or names_model_file(base_url, model)


@dataclass(frozen=True)
class LlmProviderConfig:
    base_url: str
    # "" for endpoints that don't need auth (LM Studio / Ollama local).
    api_key: str = field(repr=False)
    model: str

    @property
    def names_model_file(self) -> bool:
        return names_model_file(self.base_url, self.model)
