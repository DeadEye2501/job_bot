"""Пробные обращения к поставщику модели."""

from __future__ import annotations

import logging
import time
from typing import Any, Callable

import httpx

from adapters import lm_studio
from adapters.lm_studio import LlmProviderConfig


logger = logging.getLogger(__name__)


async def _do_list_models_for_creds(
    base_url: str, api_key: str, *, kind: str | None = None
) -> dict:
    """Best-effort fetch списка моделей. Никогда не raise — на ошибку
    отдаём {ok: False, error: ...}, на успех — {ok: True, models: [...]}.
    Если ``kind`` задан, передаём в адаптер для type-фильтра (LM Studio
    API v0 различает llm / embeddings).
    """
    cfg = LlmProviderConfig(base_url=base_url, api_key=api_key, model="x")
    client = lm_studio.make_client(cfg)
    try:
        models = await lm_studio.list_models(client, kind=kind)
        return {"ok": True, "models": models}
    except Exception as e:
        # httpx иногда сериализует request включая Authorization-header
        # в repr exception'а. Прогоняем через root-logger SecretRedaction-
        # Filter руками — он висит на root, но мы тут просто текст
        # формируем без logger.* вызова.
        from backend.log_secrets import _redact
        return {"ok": False, "error": _redact(f"{type(e).__name__}: {e}")}
    finally:
        await client.aclose()


async def _do_llm_probe(
    cfg: LlmProviderConfig,
    check_fn: Callable[[httpx.AsyncClient, str], Any],
) -> tuple[bool, str, list[str], int]:
    """Запускает chat/embed-проверку и возвращает кортеж (ok, detail, models, latency_ms).

    `client.aclose()` гарантирован через finally — иначе при cancellation
    httpx-сокет утекает.
    """
    client = lm_studio.make_client(cfg)
    t0 = time.monotonic()
    try:
        ok, detail = await check_fn(client, cfg.model)
        latency_ms = int((time.monotonic() - t0) * 1000)
        models: list[str] = []
        if ok:
            try:
                models = await lm_studio.list_models(client)
            except Exception as e:
                logger.debug("post-check list_models failed: %s", e)
        return ok, detail, models, latency_ms
    finally:
        await client.aclose()
