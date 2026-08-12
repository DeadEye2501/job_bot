"""OpenAI-compatible LLM provider client.

Despite the historical module name, this works against any OpenAI-compatible
endpoint: LM Studio, Ollama, OpenAI itself, OpenRouter, Grok, custom vLLM, etc.
"""
import logging
from dataclasses import dataclass

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


@dataclass(frozen=True)
class ChatRequest:
    """Одно обращение к чат-модели: что спрашиваем и в каких рамках.

    Свёрнуто в предмет, а не разложено доводами, потому что это одна группа:
    рамки обращения задаются вместе и вместе же меняются, когда меняется сам
    запрос. `purpose` попадает в записи журнала — по ним потом видно, кто
    именно не дождался ответа.
    """

    purpose: str
    messages: list[dict[str, str]]
    max_tokens: int
    temperature: float = 0.0
    # Своё время ожидания нужно там, где одно обращение заведомо длиннее
    # прочих: разбор резюме на слабой локальной модели идёт минутами.
    timeout: float | None = None


@dataclass(frozen=True)
class ChatAnswer:
    """Ответ чат-модели либо причина, по которой его нет.

    Откат у зовущих разный — от `None` до «считаем проверку пройденной», — и
    остаётся по местам; сюда попадает только то, чем они этот откат выбирают.
    """

    text: str | None = None
    finish_reason: str | None = None
    error: str | None = None


async def _post_chat(
    client: httpx.AsyncClient,
    model: str,
    request: ChatRequest,
    log: logging.Logger,
):
    """Обратиться к провайдеру: ответ либо готовый отказ, второе пусто.

    Сеть и отказ провайдера разбираются здесь, а не у зовущих: иначе этот
    же разбор пришлось бы писать заново в каждом месте, где к модели
    обращаются.
    """
    body = {
        "model": model,
        "messages": request.messages,
        "max_tokens": request.max_tokens,
        "temperature": request.temperature,
    }
    # Своё время ожидания подставляется, только когда оно задано: у httpx
    # явный `timeout=None` означает «ждать без предела», а не «как у клиента».
    extra = {} if request.timeout is None else {"timeout": request.timeout}
    try:
        r = await client.post("/v1/chat/completions", json=body, **extra)
        r.raise_for_status()
    except httpx.HTTPStatusError as e:
        log.warning(
            "%s: провайдер ответил HTTP %s", request.purpose, e.response.status_code
        )
        return None, ChatAnswer(error=f"llm_http_error: {e.response.status_code}")
    except httpx.RequestError as e:
        log.warning(
            "%s: запрос не дошёл: %s: %s", request.purpose, type(e).__name__, e
        )
        return None, ChatAnswer(error=f"llm_request_error: {type(e).__name__}")
    return r, None


def _warn_if_truncated(finish_reason, purpose: str, log: logging.Logger) -> None:
    """Пожаловаться в журнал, если модель упёрлась в предел токенов.

    Жалоба здесь, а не у зовущих: признак приходит сюда, имя обращения —
    тоже. Сам обрыв не отказ: обрезанный ответ иногда разбирается, и решает
    это зовущий.

    Запись досталась всем семерым, а раньше её писали двое, и у одного из
    пяти новых суждение точнее: `generate_cover_letter` считает обрыв бедой
    только у письма, не кончившегося точкой. Пусть так: здесь записан факт
    (модель не договорила), а решение о нём остаётся наверху и у него.
    """
    if finish_reason == "length":
        log.warning(
            "%s: модель упёрлась в предел токенов, ответ может быть обрезан",
            purpose,
        )


def _answer_or_empty(
    content, finish_reason, purpose: str, log: logging.Logger
) -> ChatAnswer:
    """Ответ модели или отказ «пусто».

    Пусто здесь всё, из чего не выходит текста: `null`, содержимое блоками
    (`"content": []` шлют провайдеры, совместимые с OpenAI наполовину) и
    строка из одних пробелов — так отвечает рассуждающая модель, потратившая
    весь предел токенов на размышление.

    Первые две разбираются проверкой, а не перехватом: `.strip()` у них дал
    бы `AttributeError`, который в ловушку зовущего не входит и ушёл бы ему
    исключением вместо его отката. Третья опаснее двух первых именно тем,
    что не падает: пустой текст доезжает до приговора зовущего и читается
    как «в объявлении ничего нет», то есть отказ провайдера превращается в
    приговор объявлению.
    """
    if not isinstance(content, str) or not content.strip():
        log.warning("%s: провайдер ответил без содержимого", purpose)
        return ChatAnswer(error="empty_content")
    return ChatAnswer(text=content.strip(), finish_reason=finish_reason)


async def chat(
    client: httpx.AsyncClient,
    model: str,
    request: ChatRequest,
    log: logging.Logger,
) -> ChatAnswer:
    """Спрашивает чат-модель и отдаёт текст с признаком завершения.

    Сеть, отказ провайдера и неразбираемый ответ разбираются здесь: наружу
    уходит `error`, по которому зовущий выбирает свой откат.

    Пишет в журнал логгером зовущего, а не своим: в окне журнала у строки
    виден источник, и обращения семерых иначе схлопнулись бы в одно имя.
    """
    r, refusal = await _post_chat(client, model, request, log)
    if refusal is not None:
        return refusal
    try:
        choice = r.json()["choices"][0]
        content = choice["message"]["content"]
        finish_reason = choice.get("finish_reason")
    except (IndexError, KeyError, TypeError, ValueError) as e:
        log.warning("%s: ответ провайдера не разобрать: %s", request.purpose, e)
        return ChatAnswer(error=f"malformed_response: {e}")
    # Жалоба о пределе идёт до проверки на пустоту нарочно: так отвечает
    # модель, потратившая весь предел на размышление, и выйди отказ раньше —
    # журнал называл бы симптом, умалчивая о единственной причине, с которой
    # можно что-то сделать.
    _warn_if_truncated(finish_reason, request.purpose, log)
    return _answer_or_empty(content, finish_reason, request.purpose, log)


def make_client(config: LlmProviderConfig) -> httpx.AsyncClient:
    headers: dict[str, str] = {}
    if config.api_key:
        headers["Authorization"] = f"Bearer {config.api_key}"
    return httpx.AsyncClient(
        base_url=config.base_url,
        timeout=LLM_REQUEST_TIMEOUT_SEC,
        headers=headers,
    )


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


async def _check_model(
    client: httpx.AsyncClient, model: str, kind: str
) -> tuple[bool, str]:
    """Есть ли модель у провайдера и отвечает ли она.

    Ответ читает окно настроек: `True` с именем модели либо `False` с
    причиной, годной для подсказки. Наружу уходит короткое «род и текст» —
    трассировка нужна там, где её потом читают, то есть в журнале.
    """
    named = "чата" if kind == "chat" else "векторов"
    try:
        # Без рода нарочно: проверяется вхождение в полный перечень
        # провайдера. Отбор по роду у тех, кто рода не отдаёт, идёт гаданием
        # по имени, и живая модель с неудачным именем стала бы «отсутствующей».
        models = await list_models(client)
    except Exception as e:
        _log.exception("провайдер не отдал список моделей для %s", named)
        return False, f"{type(e).__name__}: {e}"

    if model not in models:
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


async def check_chat(client: httpx.AsyncClient, model: str) -> tuple[bool, str]:
    """Проверить чат-модель. Зовётся окном настроек по имени рода."""
    return await _check_model(client, model, "chat")


async def check_embed(client: httpx.AsyncClient, model: str) -> tuple[bool, str]:
    """Проверить модель векторов. Зовётся окном настроек по имени рода."""
    return await _check_model(client, model, "embed")


# Топовые семейства моделей встраиваний в Ollama / OpenAI: `bge-*` (BAAI),
# `e5-*` (Microsoft), `nomic-embed-*` (Nomic), `text-embedding-*` (OpenAI).
# Голое «ada» приметой не годится: поймало бы «yi-chat-ada» и «llama-canada»
# и спрятало бы их из выбора чат-моделей.
_EMBED_MARKERS = ("embed", "text-embedding-", "bge-", "e5-", "nomic-")


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
