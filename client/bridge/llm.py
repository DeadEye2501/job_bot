"""Поставщик модели для окна: проверить связь, спросить имена, выбрать файл модели."""

from __future__ import annotations

import logging
import time
from functools import partial
from typing import Any, Callable

import httpx

from adapters import lm_models, lm_studio
from backend.models import LlmConfigKind
from backend.provider_config import (
    MODEL_FILE_SUFFIX,
    LlmProviderConfig,
    provider_complete,
    serves_kind,
)
from client.bridge.answer import BAD_PAYLOAD, Denied, bad_fields, reply
from client.bridge.desktop import chosen_path, closed_dialog
from client.bridge.refusals import LLM_FIELDS_REQUIRED


logger = logging.getLogger(__name__)

_MODEL_FILTER = f"Модель GGUF (*{MODEL_FILE_SUFFIX})"

# Рода поставщиков, какими их называет окно, — значения перечисления базы.
PROVIDER_KINDS = tuple(kind.value for kind in LlmConfigKind)


def _client_or_reason(cfg: LlmProviderConfig) -> tuple[httpx.AsyncClient | None, str]:
    """Клиент поставщика либо причина, по которой он не собрался.

    Сборка спотыкается о негодный адрес — `http://localhost:12ab` человек
    набирает легко. Отвечаем исходом, а не броском: поломка, вылетевшая мимо
    конверта, приезжает окну без рода, а без рода оно не знает, у которой из
    двух проверок гасить ожидание.

    Спрашивают это оба разговора с поставщиком — проба связи и опрос имён, — и
    спотыкаются они об один и тот же адрес из одной и той же формы.
    """
    try:
        return lm_studio.make_client(cfg), ""
    except Exception as e:
        logger.exception("не собрался клиент поставщика: %s", cfg.base_url)
        return None, f"Неверный адрес поставщика: {e}"


async def _do_list_models_for_creds(
    base_url: str, api_key: str, *, kind: str | None = None
) -> dict:
    """Best-effort fetch списка моделей. Никогда не raise — на ошибку
    отдаём {ok: False, error: ...}, на успех — {ok: True, models: [...]}.
    Если ``kind`` задан, передаём в адаптер для type-фильтра (LM Studio
    API v0 различает llm / embeddings).
    """
    cfg = LlmProviderConfig(base_url=base_url, api_key=api_key, model="x")
    client, reason = _client_or_reason(cfg)
    if client is None:
        return {"ok": False, "error": reason}
    try:
        models = await lm_models.list_models(client, kind=kind)
        return {"ok": True, "models": models}
    except Exception as e:
        # Человеку в плашку едет короткая фраза, и по ней не отличить
        # неподнятого поставщика от оборванной сети или чужого ответа. След
        # остаётся только здесь: дальше беда уходит исходом, а не броском.
        logger.exception("не вышло спросить имена моделей у %s", base_url)
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
    client, reason = _client_or_reason(cfg)
    if client is None:
        return False, reason, [], 0
    t0 = time.monotonic()
    try:
        ok, detail = await check_fn(client, cfg.model)
        latency_ms = int((time.monotonic() - t0) * 1000)
        models: list[str] = []
        if ok:
            try:
                models = await lm_models.list_models(client)
            except Exception as e:
                logger.debug(
                    "post-check list_models failed: %s", e, exc_info=True
                )
        return ok, detail, models, latency_ms
    finally:
        await client.aclose()


def read_llm_creds(payload: dict, kind: str) -> LlmProviderConfig:
    """Черновые учётные данные поставщика из нагрузки окна.

    Читаются одним правилом на всех, кто спрашивает поставщика: проба связи и
    запись обоих поставщиков. Прежде правил было три — мастер ронял разбор на
    пропущенном поле, окно подставляло пустую строку, настройки смотрели только
    на модель, — и одна и та же форма принималась по-разному в зависимости от
    того, откуда её открыли.

    Пустой адрес или пустое имя модели роняет `ValueError`: сохранённая
    пустота выглядит как настроенный поставщик, и беду ищут потом где угодно,
    только не здесь. Адрес не нужен одному — файлу модели эмбеддингов на диске,
    поэтому правило спрашивает род поставщика.
    """
    if not isinstance(payload, dict):
        raise ValueError(LLM_FIELDS_REQUIRED)
    base_url, api_key = _provider_address(payload)
    model = str(payload.get("model") or "").strip()
    if not provider_complete(kind, base_url, model):
        raise ValueError(LLM_FIELDS_REQUIRED)
    return LlmProviderConfig(base_url=base_url, api_key=api_key, model=model)


def read_models_ask(payload) -> tuple[str, str, str]:
    """О чём спрашивают поставщика: род, адрес и ключ."""
    payload = payload if isinstance(payload, dict) else {}
    return (str(payload.get("kind") or ""), *_provider_address(payload))


def _provider_address(payload: dict) -> tuple[str, str]:
    """Адрес поставщика и ключ доступа, приведённые к записи.

    Хвостовая косая у адреса срезается: человек копирует адрес из браузера
    вместе с ней, а склейка пути дала бы двойную.

    Одним объявлением на обоих, кто это читает, — на запись поставщика и на
    опрос имён. Разъедься приведение, один и тот же набранный адрес принимался
    бы по-разному в зависимости от того, в каком поле его набрали.
    """
    return (
        str(payload.get("base_url") or "").strip().rstrip("/"),
        str(payload.get("api_key") or ""),
    )


class Llm:
    """Проверка модели и опрос её имён по просьбе окна.

    Проверяют они не сохранённые настройки, а присланные окном черновые —
    человек должен увидеть исход до записи. Собирающий обязан держать `_hub`:
    оттуда берётся мотор.
    """

    def probe_model(self, payload: dict) -> dict:
        """Проверка связи с поставщиком: перечень имён и однословный вопрос.

        Нагрузка: `{kind: 'chat'|'embed', base_url, api_key, model}` —
        черновая, из формы, а не сохранённая: человек должен узнать исход до
        записи. Мерится время всей проверки, вместе с перечнем имён.

        Род уезжает обратно в каждом ответе, включая отказы: проверок на экране
        две, и без рода окно не знает, у которой из них показывать исход.
        """
        kind = ""
        try:
            payload = payload if isinstance(payload, dict) else {}
            kind = str(payload.get("kind", "")).strip()
            if kind not in PROVIDER_KINDS:
                raise ValueError(f"неизвестный род: {kind!r}")
            cfg = read_llm_creds(payload, kind)
        except BAD_PAYLOAD as e:
            return bad_fields("probe_model", e, kind=kind)

        check_fn = partial(lm_models.check_model, kind=kind)

        async def run() -> dict:
            ok, detail, _models, latency_ms = await _do_llm_probe(cfg, check_fn)
            if not ok:
                raise Denied(detail, kind=kind)
            return {"kind": kind, "model": cfg.model, "latency_ms": latency_ms}

        return reply(self._hub.runner, run())

    def pick_model_file(self) -> dict:
        """Спросить у человека файл модели эмбеддингов диалогом самого окна.

        Только называет путь, не записывает: записывает страница тем же
        `settings.save`, что и адрес сервера, — в настройках сразу, в мастере
        по «Дальше». Закрытый диалог — не отказ, а «передумал».
        """
        path = chosen_path(self._hub.window, _MODEL_FILTER)
        if path is None:
            return closed_dialog()
        return {"ok": {"path": path}}

    def list_models(self, payload: dict) -> dict:
        """Имена моделей у поставщика — окно подсказывает ими поле «Модель».

        Под LM Studio спрашивается `/api/v0/models` с отбором по роду и
        состоянию, с откатом на `/v1/models` (см. `lm_models.list_models`):
        в подсказке должны стоять только поднятые модели подходящего рода,
        иначе первая же проба тихо подгрузит выгруженную.

        Недописанный адрес и незнакомый род — не отказ, а пустой перечень:
        спрашивают на каждый набранный знак, и плашка отказа мигала бы на
        каждой букве.
        """
        kind, base_url, api_key = read_models_ask(payload)

        async def run() -> dict:
            if not base_url or kind not in PROVIDER_KINDS:
                return {"kind": kind, "models": []}
            # Векторов Claude не считает: перечень его моделей в поле эмбеддингов
            # подсказывал бы то, что не заработает.
            if not serves_kind(kind, base_url):
                return {"kind": kind, "models": []}
            answer = await _do_list_models_for_creds(base_url, api_key, kind=kind)
            if not answer["ok"]:
                raise Denied(answer["error"], kind=kind)
            return {"kind": kind, "models": answer["models"]}

        return reply(self._hub.runner, run())
