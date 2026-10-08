"""Claude через официальный SDK Anthropic: соединение, запрос и перечень моделей.

Надстройка рядом с OpenAI-совместимым путём: нынешние точки входа
(`lm_studio`, `lm_chat`, `lm_models`) узнают этот клиент по типу и отдают
его сюда. Здесь то, чем Claude отличается: системный промпт отдельным
параметром, отсутствие temperature, блоки в ответе, отказ модели. Метки бед
и проверка ответа остаются общими у точек входа.
"""

import logging
from urllib.parse import urlsplit

import anthropic

from backend.runtime_settings import LlmProviderConfig

_log = logging.getLogger(__name__)

CLAUDE_HOST = "api.anthropic.com"

# Адрес клиента — всегда корень, а не то, что набрано: SDK сам дописывает
# `/v1/...`, и набранный с `/v1` адрес давал бы `/v1/v1/messages` и 404,
# который человек прочёл бы как «модели нет».
_CLAUDE_URL = f"https://{CLAUDE_HOST}"

# Размышление расходует тот же предел, что и ответ. Пределы в `backend/llm`
# подобраны под локальную модель без размышления, и Claude обрывался бы на
# них, не дойдя до ответа.
MIN_MAX_TOKENS = 16000
EFFORT = "medium"

# Причина конца «модель отказалась отвечать». В словаре OpenAI её нет, и
# зовущий отличает её от обрыва и от ответа именно по этому слову.
REFUSED = "refusal"

NO_EMBEDDINGS = "У Anthropic нет моделей эмбеддингов"

# Причины конца в словаре OpenAI: по `length` зовущие решают про обрыв. Окно
# контекста, исчерпанное посреди ответа, — тот же обрыв.
_FINISH = {
    "max_tokens": "length",
    "model_context_window_exceeded": "length",
    "end_turn": "stop",
}


class MissingKey(Exception):
    """Ключ Anthropic не указан — спрашивать модель не с чем."""


class ClaudeClient(anthropic.AsyncAnthropic):
    """Клиент SDK, который закрывается так же, как httpx-клиент соседей."""

    async def aclose(self) -> None:
        await self.close()


def serves(base_url: str) -> bool:
    """Ведёт ли адрес к Anthropic."""
    return urlsplit(base_url).hostname == CLAUDE_HOST


def make_client(config: LlmProviderConfig, *, timeout: float) -> ClaudeClient:
    """Клиент Anthropic по настройкам поставщика.

    Ключ передаётся всегда, даже пустой: без него SDK взял бы ключ из
    окружения, и приложение ходило бы к модели по чужому ключу.
    """
    return ClaudeClient(api_key=config.api_key, base_url=_CLAUDE_URL, timeout=timeout)


def _require_key(client: ClaudeClient) -> None:
    """Отказать до похода в сеть, если ключа нет.

    С пустым ключом SDK бросает `TypeError` при сборке заголовков — мимо своих
    ошибок и мимо всех перехватов зовущих. А пустой ключ — обычное состояние
    мастера: пресет выбран, ключ ещё не вписан.
    """
    if not client.api_key:
        raise MissingKey("Не указан ключ Anthropic")


def _params(model: str, messages: list[dict[str, str]], max_tokens: int) -> dict:
    """Тело запроса: системные сообщения — в `system`, остальные — в `messages`."""
    system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
    params = {
        "model": model,
        "max_tokens": max(max_tokens, MIN_MAX_TOKENS),
        "messages": [m for m in messages if m["role"] != "system"],
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": EFFORT},
    }
    if system:
        params["system"] = system
    return params


async def ask(client: ClaudeClient, model: str, request, log: logging.Logger):
    """Спросить модель: текст и причина конца в словаре OpenAI.

    `request` — `lm_chat.ChatRequest`; тип не назван, потому что `lm_chat` сам
    зовёт этот модуль, и импорт навстречу замкнул бы круг.

    Ошибки SDK и `MissingKey` уходят наверх: метку им ставит `lm_chat`, одну на
    оба пути. Отказ модели — не ошибка, а ответ без текста с причиной `REFUSED`.
    """
    _require_key(client)
    target = client if request.timeout is None else client.with_options(timeout=request.timeout)
    reply = await target.messages.create(
        **_params(model, request.messages, request.max_tokens)
    )
    if reply.stop_reason == REFUSED:
        category = reply.stop_details.category if reply.stop_details else None
        log.warning("%s: модель отказалась отвечать (%s)", request.purpose, category)
        return None, REFUSED
    text = "".join(block.text for block in reply.content if block.type == "text")
    return text, _FINISH.get(reply.stop_reason, reply.stop_reason)


async def list_models(client: ClaudeClient, kind: str | None = None) -> list[str]:
    """Модели, доступные ключу. Эмбеддингов у Anthropic нет — для них пусто."""
    if kind == "embed":
        return []
    _require_key(client)
    return [one.id async for one in client.models.list()]


async def ping(client: ClaudeClient, model: str) -> tuple[bool, str]:
    """Пробный запрос с теми же параметрами, что у настоящих.

    Голый запрос прошёл бы и у модели, которая не принимает размышления или
    уровня, — кнопка проверки зеленела бы, а каждый настоящий запрос получал
    бы 400.
    """
    try:
        await client.messages.create(
            **_params(model, [{"role": "user", "content": "ping"}], max_tokens=16)
        )
    except anthropic.APIError as e:
        _log.exception("пробный запрос к модели %s не прошёл", model)
        return False, f"{model} (ping failed: {type(e).__name__})"
    return True, model

