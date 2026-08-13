"""Разговор с поставщиком модели: проба связи и опрос имён."""

from __future__ import annotations

import json
import logging
import time
from functools import partial
from typing import Any, Callable

import httpx
from PySide6.QtCore import Signal, Slot

from adapters import lm_studio
from adapters.lm_studio import LlmProviderConfig
from client.bridge.answer import _err, _ok
from client.bridge.payload import _log_invalid_payload
from client.bridge.refusals import LLM_FIELDS_REQUIRED


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


def read_llm_creds(payload: dict) -> LlmProviderConfig:
    """Черновые учётные данные поставщика из нагрузки окна.

    Читаются одним правилом на всех, кто спрашивает поставщика: проба, обе
    проверки мастера и оба его сохранения, оба сохранения настроек. Прежде
    правил было три — мастер ронял разбор на пропущенном поле, окно
    подставляло пустую строку, настройки смотрели только на модель, — и одна
    и та же форма принималась по-разному в зависимости от того, откуда её
    открыли.

    Хвостовая косая у адреса срезается: человек копирует адрес из браузера
    вместе с ней, а склейка пути дала бы двойную.

    Пустой адрес или пустое имя модели роняет `ValueError`: сохранённая
    пустота выглядит как настроенный поставщик, и беду ищут потом где угодно,
    только не здесь.
    """
    if not isinstance(payload, dict):
        raise ValueError(LLM_FIELDS_REQUIRED)
    base_url = str(payload.get("base_url") or "").strip().rstrip("/")
    api_key = str(payload.get("api_key") or "")
    model = str(payload.get("model") or "").strip()
    if not base_url or not model:
        raise ValueError(LLM_FIELDS_REQUIRED)
    return LlmProviderConfig(base_url=base_url, api_key=api_key, model=model)


def models_coro(payload_json: str):
    """Корутина ответа «какие модели у поставщика есть», или пусто.

    Пусто значит «спрашивать нечего» — нет адреса или неизвестен род; окну в
    этом случае не отвечают вовсе, потому что оно спрашивает на каждый
    набранный знак адреса.

    Одна на два окна: мастер и настройки спрашивают одно и то же и отдают
    ответ каждый в свой сигнал — имена сигналов знает разметка, и сводить их
    этому этапу нельзя.
    """
    try:
        payload = json.loads(payload_json) if payload_json else {}
        kind = str(payload.get("kind") or "")
        base_url = str(payload.get("base_url") or "").strip().rstrip("/")
        api_key = str(payload.get("api_key") or "")
    except (AttributeError, ValueError, TypeError):
        return None
    if not base_url or kind not in ("chat", "embed"):
        return None

    async def run() -> str:
        result = await _do_list_models_for_creds(base_url, api_key, kind=kind)
        return json.dumps({"kind": kind, **result})

    return run()


class LlmSlots:
    """Проверка модели и опрос её имён по просьбе окна.

    Проверяют они не сохранённые настройки, а присланные окном черновые —
    человек должен увидеть исход до записи. Подмешивающий обязан держать
    `_dispatch`.
    """

    llm_probe_done = Signal(str)
    llm_models_listed = Signal(str)

    @Slot(str)
    def request_llm_probe(self, payload_json: str) -> None:
        """Connectivity check for an LLM provider (chat / embed).

        Payload: ``{kind: 'chat'|'embed', base_url, api_key, model}``.
        Использует draft-значения из UI, не текущий rs — чтобы юзер мог
        проверить новые настройки до сохранения. Замеряем latency полного
        check'а (list_models + 1-token ping).
        """
        # Init defaults ДО try, чтобы все error-ветки могли echo'нуть kind
        # обратно — JS использует его для роутинга в нужный *Probe-state.
        kind = ""
        try:
            payload = json.loads(payload_json) if payload_json else {}
            kind = str(payload.get("kind", "")).strip()
            if kind not in ("chat", "embed"):
                raise ValueError(f"bad kind: {kind!r}")
            cfg = read_llm_creds(payload)
        except (ValueError, TypeError) as e:
            _log_invalid_payload("request_llm_probe", e)
            self.llm_probe_done.emit(_err(f"Неверные поля: {e}", kind=kind))
            return

        check_fn = partial(lm_studio.check_model, kind=kind)

        async def run() -> str:
            try:
                ok, detail, _models, latency_ms = await _do_llm_probe(cfg, check_fn)
            except Exception as e:
                logger.exception("llm probe failed")
                return _err(f"{type(e).__name__}: {e}", kind=kind)
            if not ok:
                return _err(detail, kind=kind)
            return _ok({"kind": kind, "model": cfg.model, "latency_ms": latency_ms})

        self._dispatch(self.llm_probe_done, run())

    @Slot(str)
    def request_llm_models(self, payload_json: str) -> None:
        """Background-fetch списка моделей — UI наполняет datalist для
        автокомплита поля «Модель». Под LM Studio предпочтительно
        ``/api/v0/models`` с фильтром по type/state (см. lm_studio.list_models),
        фолбэк на OpenAI-совместимый ``/v1/models``. Best-effort, ошибки в
        payload."""
        coro = models_coro(payload_json)
        if coro is not None:
            self._dispatch(self.llm_models_listed, coro)
