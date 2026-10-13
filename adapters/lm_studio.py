"""Соединение с OpenAI-совместимым провайдером моделей.

Несмотря на историческое имя, годится любой такой провайдер: LM Studio,
Ollama, OpenAI, OpenRouter, vLLM. Здесь только соединение; разговор с
чат-моделью, перечень моделей и отпечатки живут у соседей (`lm_chat`,
`lm_models`, `lm_embed`). Адрес Anthropic получает клиента SDK из
`adapters/claude`, адрес `claude-code` — клиента Claude Code из
`adapters/claude_code`, путь к файлу модели без адреса — клиента из
`adapters/gguf_embed`.
"""

import httpx

from adapters import claude, claude_code, gguf_embed
from backend.provider_config import LlmProviderConfig, serves_claude, serves_claude_code


# Большие локальные модели (Qwen3 30B, Llama 70B и т.п.) на длинном
# `validate_role_fit` или `parse_vacancy` промпте уходят за 30 сек на
# обычном железе — особенно при первом запуске после загрузки модели,
# когда часть слоёв ещё подкачивается. Жёсткий 30-сек лимит приводит к
# массовому "validation unavailable" → вакансии пачкой попадают в Not Fit
# по таймауту, а не по содержанию. Удалённые провайдеры (OpenAI/OpenRouter)
# обычно отвечают быстро, для них этот лимит избыточен, но не критичен.
LLM_REQUEST_TIMEOUT_SEC = 180.0


def make_client(
    config: LlmProviderConfig,
) -> "LmClient":
    if serves_claude(config.base_url):
        return claude.make_client(config, timeout=LLM_REQUEST_TIMEOUT_SEC)
    if serves_claude_code(config.base_url):
        return claude_code.make_client(timeout=LLM_REQUEST_TIMEOUT_SEC)
    if config.names_model_file:
        return gguf_embed.ModelFile(config.model)
    headers: dict[str, str] = {}
    if config.api_key:
        headers["Authorization"] = f"Bearer {config.api_key}"
    # Пути запросов (`/v1/chat/completions` и соседи) дописывают `/v1` сами, а
    # адрес провайдера пишут и с ним, и без: хвостовой `/v1` снимается, иначе
    # запрос уходил бы на `/v1/v1/...` и получал 404.
    return httpx.AsyncClient(
        base_url=config.base_url.rstrip("/").removesuffix("/v1"),
        timeout=LLM_REQUEST_TIMEOUT_SEC,
        headers=headers,
    )


# Клиент любого поставщика, какого собирает `make_client`: точки входа
# (`lm_chat`, `lm_models`, `lm_embed`) различают их по типу.
LmClient = (
    httpx.AsyncClient
    | claude.ClaudeClient
    | claude_code.ClaudeCodeClient
    | gguf_embed.ModelFile
)

