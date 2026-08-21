"""Соединение с OpenAI-совместимым провайдером моделей.

Несмотря на историческое имя, годится любой такой провайдер: LM Studio,
Ollama, OpenAI, OpenRouter, vLLM. Здесь только соединение; разговор с
чат-моделью, перечень моделей и отпечатки живут у соседей (`lm_chat`,
`lm_models`, `lm_embed`).
"""

import httpx

from backend.runtime_settings import LlmProviderConfig


# Большие локальные модели (Qwen3 30B, Llama 70B и т.п.) на длинном
# `validate_role_fit` или `parse_vacancy` промпте уходят за 30 сек на
# обычном железе — особенно при первом запуске после загрузки модели,
# когда часть слоёв ещё подкачивается. Жёсткий 30-сек лимит приводит к
# массовому "validation unavailable" → вакансии пачкой попадают в Not Fit
# по таймауту, а не по содержанию. Удалённые провайдеры (OpenAI/OpenRouter)
# обычно отвечают быстро, для них этот лимит избыточен, но не критичен.
LLM_REQUEST_TIMEOUT_SEC = 180.0


def make_client(config: LlmProviderConfig) -> httpx.AsyncClient:
    headers: dict[str, str] = {}
    if config.api_key:
        headers["Authorization"] = f"Bearer {config.api_key}"
    return httpx.AsyncClient(
        base_url=config.base_url,
        timeout=LLM_REQUEST_TIMEOUT_SEC,
        headers=headers,
    )
