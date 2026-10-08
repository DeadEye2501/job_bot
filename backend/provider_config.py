"""Поставщик модели в настройках: из каких полей он состоит и когда настроен.

Своим модулем, а не внутри `runtime_settings`: правило годности строки
спрашивают трое — подъём настроек из базы, мост окна и выбор клиента в
адаптерах, — и ни одному из них не нужен кеш настроек целиком.
"""

from dataclasses import dataclass, field

MODEL_FILE_SUFFIX = ".gguf"


def names_model_file(base_url: str | None, model: str | None) -> bool:
    """Строка поставщика указывает не на сервер, а на файл модели на диске.

    Адреса у такой строки нет, а в поле модели — путь к GGUF.
    """
    return not base_url and bool(model) and model.lower().endswith(MODEL_FILE_SUFFIX)


def provider_complete(kind: str, base_url: str | None, model: str | None) -> bool:
    """Годится ли строка в поставщика рода `kind` ('chat' | 'embed').

    Модель названа, и есть, где её взять: адрес сервера, а у эмбеддингов ещё
    и файл модели на диске. Чат из файла не говорит — такой клиент бот собрал
    бы и падал бы на каждом разговоре. Правило одно на подъём из базы и на
    окно: разъедься они, строка, принятая окном, не поднималась бы ботом.
    """
    if not model:
        return False
    return bool(base_url) or (kind == "embed" and names_model_file(base_url, model))


@dataclass(frozen=True)
class LlmProviderConfig:
    base_url: str
    # "" for endpoints that don't need auth (LM Studio / Ollama local).
    api_key: str = field(repr=False)
    model: str

    @property
    def names_model_file(self) -> bool:
        return names_model_file(self.base_url, self.model)
