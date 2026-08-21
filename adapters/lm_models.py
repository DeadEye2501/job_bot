"""Перечень моделей у провайдера и проверка, что нужная отвечает.

Спрашивают отсюда двое: мастер настройки, который показывает человеку выбор,
и проверка связи. Род модели — чат или встраивания — провайдеры отдают не
всегда, и тогда его угадывают по имени.
"""

import logging

import httpx

_log = logging.getLogger(__name__)


def _ping_request(model: str, kind: str) -> tuple[str, dict]:
    """Чем щупается модель рода: путь и тело пробного запроса.

    Пробный запрос настоящий, а не запрос списка: модель может числиться у
    провайдера и не отвечать — из-за нехватки памяти, чужой занятости или
    несовместимости с родом обращения.
    """
    if kind == "chat":
        return "/v1/chat/completions", {
            "model": model,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 1,
        }
    return "/v1/embeddings", {"model": model, "input": "ping"}


async def model_listed(
    client: httpx.AsyncClient, model: str
) -> tuple[bool, list[str]]:
    """Числится ли модель у провайдера, и что у него есть вообще.

    **Перечень спрашивается без рода, и это здесь главное.** Отбор по роду у
    провайдеров, которые рода не отдают, идёт гаданием по имени, и живая
    модель с неудачным именем стала бы «отсутствующей». А довод рода уводит
    на родной путь LM Studio, который отбирает только загруженные, — и
    простоявшая полчаса модель числилась бы отсутствующей тоже.

    Спрашивают отсюда двое, и вопрос у них общий: кнопка проверки связи
    добавляет к нему пробное обращение, лампочка здоровья не добавляет
    ничего. Второе значение нужно только первой — тому, кто объясняет отказ
    человеку.
    """
    models = await list_models(client)
    return model in models, models


async def check_model(
    client: httpx.AsyncClient, model: str, kind: str
) -> tuple[bool, str]:
    """Есть ли модель у провайдера и отвечает ли она.

    Спрашивает больше, чем лампочка здоровья: та берёт один `model_listed`, а
    здесь к нему добавлено пробное обращение — модель числится и не отвечает
    чаще, чем кажется, из-за нехватки памяти или несовместимости с родом
    обращения. Расхождение между кнопкой и лампочкой принято сознательно:
    почему — сказано у `backend.health.model_alive`.

    Ответ читает окно настроек: `True` с именем модели либо `False` с
    причиной, годной для подсказки. Наружу уходит короткое «род и текст» —
    трассировка нужна там, где её потом читают, то есть в журнале.
    """
    named = "чата" if kind == "chat" else "векторов"
    try:
        listed, models = await model_listed(client, model)
    except Exception as e:
        _log.exception("провайдер не отдал список моделей для %s", named)
        return False, f"{type(e).__name__}: {e}"

    if not listed:
        preview = ", ".join(models[:3]) or "no models loaded"
        return False, f"{model!r} not available (have: {preview})"

    path, body = _ping_request(model, kind)
    try:
        r = await client.post(path, json=body)
    except httpx.HTTPError as e:
        _log.exception("пробный запрос к модели %s для %s не прошёл", model, named)
        return False, f"{type(e).__name__}: {e}"
    if not r.is_success:
        return False, f"{model} (ping failed: HTTP {r.status_code})"
    return True, model


# Приметы моделей встраиваний. Первая — `embed` внутри имени — покрывает и
# `nomic-embed-*`, и `text-embedding-*`, и всё прочее с этим корнем; остальные
# три добраны под семейства, где корня нет вовсе: `bge-*` (BAAI), `e5-*`
# (Microsoft) и весь `nomic-*` целиком, включая имена без `embed`.
# Голое «ada» приметой не годится: поймало бы «yi-chat-ada» и «llama-canada»
# и спрятало бы их из выбора чат-моделей.
_EMBED_MARKERS = ("embed", "bge-", "e5-", "nomic-")


def _looks_like_embed(name: str) -> bool:
    """Похоже ли имя модели на встраивания.

    Гадание по имени — единственное, что остаётся у провайдеров, чей
    `/v1/models` рода не отдаёт. Без него встраивания протекают в выбор
    чат-моделей и наоборот, а выбравший не то получает «not a chat model».
    """
    lowered = name.lower()
    return any(mark in lowered for mark in _EMBED_MARKERS)


async def _loaded_models(client: httpx.AsyncClient, kind: str) -> list[str] | None:
    """Загруженные модели рода у LM Studio, либо `None`, если пути нет.

    Родной путь LM Studio знает и род модели, и то, загружена ли она.
    `/v1/models` у неё отдаёт все настроенные, и выбор выгруженной запускает
    подкачку на полминуты — для выбора в окне это негодно.

    Два пустых ответа тут разные, и путать их нельзя. `None` — родного пути у
    провайдера нет, спрашивать надо `/v1/models`. Пустой список — путь есть и
    ответил: этого рода не загружено ничего. Спросить после него `/v1/models`
    значило бы вернуть в окно ровно те выгруженные модели, ради которых
    родной путь и заведён.
    """
    try:
        r = await client.get("/api/v0/models")
        if not r.is_success:
            _log.debug(
                "LM Studio /api/v0/models returned HTTP %s; falling back to /v1/models",
                r.status_code,
            )
            return None
        data = r.json().get("data") or []
    except Exception:
        # Сюда влетает, например, если /api/v0/models вернул не-JSON
        # (Ollama / OpenAI proper). Уровень отладочный нарочно: у провайдера
        # без родного пути это не беда, а обычный ход.
        _log.debug("/api/v0/models probe failed; falling back to /v1/models", exc_info=True)
        return None
    wanted_type = "llm" if kind == "chat" else "embeddings"
    return [
        m["id"]
        for m in data
        if isinstance(m, dict)
        and m.get("id")
        and m.get("state") == "loaded"
        and m.get("type") == wanted_type
    ]


async def list_models(client: httpx.AsyncClient, *, kind: str | None = None) -> list[str]:
    """Return ids of models exposed by the provider.

    С родом ('chat' | 'embed') сперва спрашивается родной путь LM Studio —
    он один умеет отобрать загруженные (см. `_loaded_models`). Без рода
    (например, для проверки связи) — полный список через совместимый с OpenAI
    ``/v1/models``.
    """
    if kind is not None:
        loaded = await _loaded_models(client, kind)
        if loaded is not None:
            return loaded
        # Родного пути нет: полный список, и род придётся угадывать по имени —
        # ни ``state``, ни ``type`` в нём не приходит.
    r = await client.get("/v1/models")
    r.raise_for_status()
    ids = [m["id"] for m in r.json().get("data", []) if isinstance(m, dict) and m.get("id")]
    if kind is None:
        return ids
    if kind == "embed":
        return [i for i in ids if _looks_like_embed(i)]
    return [i for i in ids if not _looks_like_embed(i)]
