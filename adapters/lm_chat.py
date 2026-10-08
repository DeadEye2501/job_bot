"""Обращение к чат-модели провайдера и разбор её ответа.

Провайдер любой OpenAI-совместимый: LM Studio, Ollama, OpenAI, OpenRouter,
vLLM. Соединение с ним заводит сосед (`lm_studio.make_client`), здесь только
разговор: что спросили, что ответили и чем беда, если ответа нет. Клиента
Anthropic разговор отдаёт в `adapters/claude`.
"""

import logging
from dataclasses import dataclass

import anthropic
import httpx

from adapters import claude

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
        return None, _status_refusal(request.purpose, e.response.status_code, log)
    except httpx.RequestError as e:
        return None, _delivery_refusal(request.purpose, e, log)
    return r, None


def _status_refusal(purpose: str, status: int, log: logging.Logger) -> ChatAnswer:
    """Провайдер ответил кодом отказа.

    Метка одна на оба пути — OpenAI-совместимый и Claude: по ней зовущие
    выбирают откат, и разъехавшиеся метки увели бы один путь мимо него.
    """
    log.warning("%s: провайдер ответил HTTP %s", purpose, status)
    return ChatAnswer(error=f"llm_http_error: {status}")


def _delivery_refusal(
    purpose: str, trouble: Exception, log: logging.Logger
) -> ChatAnswer:
    """Запрос до провайдера не дошёл; метка общая по той же причине."""
    log.warning("%s: запрос не дошёл: %s: %s", purpose, type(trouble).__name__, trouble)
    return ChatAnswer(error=f"llm_request_error: {type(trouble).__name__}")


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
    client: httpx.AsyncClient | claude.ClaudeClient,
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
    if isinstance(client, claude.ClaudeClient):
        return await _chat_with_claude(client, model, request, log)
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


async def _chat_with_claude(
    client: claude.ClaudeClient,
    model: str,
    request: ChatRequest,
    log: logging.Logger,
) -> ChatAnswer:
    """Разговор с Claude, сведённый к тому же ответу, что у OpenAI-пути.

    Метки бед, жалоба на обрыв и проверка на пустоту — общие: беды у ответа
    те же, и вторые их копии разошлись бы с первыми.
    """
    try:
        content, finish_reason = await claude.ask(client, model, request, log)
    except claude.MissingKey:
        log.warning("%s: не указан ключ Anthropic", request.purpose)
        return ChatAnswer(error="no_api_key")
    except anthropic.APIStatusError as e:
        return _status_refusal(request.purpose, e.status_code, log)
    except anthropic.APIConnectionError as e:
        return _delivery_refusal(request.purpose, e, log)
    if finish_reason == claude.REFUSED:
        return ChatAnswer(error="refusal")
    _warn_if_truncated(finish_reason, request.purpose, log)
    return _answer_or_empty(content, finish_reason, request.purpose, log)
