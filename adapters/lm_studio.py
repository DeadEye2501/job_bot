"""OpenAI-compatible LLM provider client.

Despite the historical module name, this works against any OpenAI-compatible
endpoint: LM Studio, Ollama, OpenAI itself, OpenRouter, Grok, custom vLLM, etc.
"""
import logging

import httpx

from backend.runtime_settings import LlmProviderConfig


_log = logging.getLogger(__name__)


# Большие локальные модели (Qwen3 30B, Llama 70B и т.п.) на длинном
# `validate_vacancy_fit` или `parse_vacancy` промпте уходят за 30 сек на
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


async def check_chat(client: httpx.AsyncClient, model: str) -> tuple[bool, str]:
    """Verify the chat model is available and responds to a 1-token ping."""
    try:
        r = await client.get("/v1/models")
        r.raise_for_status()
        models = [m["id"] for m in r.json().get("data", [])]
    except Exception as e:
        # Наружу уходит короткое «род и текст» — его показывают подсказкой
        # в окне. Трассировка нужна там, где её потом читают.
        _log.exception("провайдер не отдал список моделей для чата")
        return False, f"{type(e).__name__}: {e}"

    if model not in models:
        preview = ", ".join(models[:3]) or "no models loaded"
        return False, f"{model!r} not available (have: {preview})"

    try:
        r = await client.post(
            "/v1/chat/completions",
            json={
                "model": model,
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 1,
            },
        )
    except Exception as e:
        _log.exception("пробный запрос к чат-модели %s не прошёл", model)
        return False, f"{type(e).__name__}: {e}"
    if not r.is_success:
        return False, f"{model} (ping failed: HTTP {r.status_code})"
    return True, model


async def check_embed(client: httpx.AsyncClient, model: str) -> tuple[bool, str]:
    """Verify the embedding model is available and responds."""
    try:
        r = await client.get("/v1/models")
        r.raise_for_status()
        models = [m["id"] for m in r.json().get("data", [])]
    except Exception as e:
        # Наружу уходит короткое «род и текст» — его показывают подсказкой
        # в окне. Трассировка нужна там, где её потом читают.
        _log.exception("провайдер не отдал список моделей для векторов")
        return False, f"{type(e).__name__}: {e}"

    if model not in models:
        return False, f"{model!r} not available"

    try:
        r = await client.post(
            "/v1/embeddings",
            json={"model": model, "input": "ping"},
        )
    except Exception as e:
        _log.exception("пробный запрос к модели векторов %s не прошёл", model)
        return False, f"{type(e).__name__}: {e}"
    if not r.is_success:
        return False, f"{model} (ping failed: HTTP {r.status_code})"
    return True, model


async def list_models(client: httpx.AsyncClient, *, kind: str | None = None) -> list[str]:
    """Return ids of models exposed by the provider.

    Когда ``kind`` задан ('chat' | 'embed') и провайдер поддерживает
    LM Studio's native ``/api/v0/models`` — отфильтровываем по
    ``state == "loaded"`` и ``type == "llm" | "embeddings"``. Это нужно
    для UI-picker'а: ``/v1/models`` у LM Studio возвращает ВСЕ
    настроенные модели, и выбор выгруженной триггерит JIT-load (≥ 30 сек),
    что плохой UX.

    Без ``kind`` (например, healthcheck) — поведение прежнее: полный
    список через OpenAI-совместимый ``/v1/models``.
    """
    if kind is not None:
        try:
            r = await client.get("/api/v0/models")
            if r.is_success:
                data = r.json().get("data") or []
                wanted_type = "llm" if kind == "chat" else "embeddings"
                ids: list[str] = []
                for m in data:
                    if not isinstance(m, dict) or not m.get("id"):
                        continue
                    if m.get("state") != "loaded":
                        continue
                    if m.get("type") != wanted_type:
                        continue
                    ids.append(m["id"])
                return ids
            _log.debug(
                "LM Studio /api/v0/models returned HTTP %s; falling back to /v1/models",
                r.status_code,
            )
        except Exception as e:
            # Сюда влетает, например, если /api/v0/models вернул не-JSON
            # (Ollama / OpenAI proper). Фолбэк на /v1/models — безопасный
            # путь, но без фильтра по state/type.
            _log.debug("/api/v0/models probe failed (%s); falling back to /v1/models", e)
        # Fallthrough: провайдер без /api/v0 — возвращаем полный список.
    r = await client.get("/v1/models")
    r.raise_for_status()
    ids = [m["id"] for m in r.json().get("data", []) if isinstance(m, dict) and m.get("id")]
    if kind is None:
        return ids
    # Для не-LM-Studio провайдеров (/v1/models не отдаёт type) heuristic-
    # фильтр по имени. Покрытие — топовые семейства embedding-моделей в
    # Ollama / OpenAI: `bge-*` (BAAI), `e5-*` (Microsoft), `nomic-embed-*`
    # (Nomic), `*ada*` / `text-embedding-*` (OpenAI), generic `*embed*`.
    # Без этого фильтра embedding'и протекают в chat-picker (и наоборот),
    # юзер выбирает не то — LLM-вызовы валятся с «not a chat model».
    # `text-embedding-ada-` уже покрывает OpenAI ada-семейство; bare
    # «ada» как substring опасен — поймает гипотетический «yi-chat-ada»
    # / «llama-canada-tuned» и спрячет их из chat-picker'а.
    embed_markers = (
        "embed", "text-embedding-", "bge-", "e5-", "nomic-",
    )
    def _looks_like_embed(name: str) -> bool:
        n = name.lower()
        return any(mark in n for mark in embed_markers)
    if kind == "embed":
        return [i for i in ids if _looks_like_embed(i)]
    return [i for i in ids if not _looks_like_embed(i)]


async def embed(client: httpx.AsyncClient, model: str, text: str) -> list[float]:
    r = await client.post(
        "/v1/embeddings",
        json={"model": model, "input": text},
    )
    r.raise_for_status()
    payload = r.json()
    data = payload.get("data") or []
    if not data:
        raise RuntimeError(f"embed: empty data in response: {payload!r}")
    embedding = data[0].get("embedding")
    if not isinstance(embedding, list) or not embedding:
        raise RuntimeError(
            f"embed: missing/invalid embedding in response: {payload!r}"
        )
    return embedding
