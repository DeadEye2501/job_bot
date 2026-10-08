"""Claude через официальный SDK Anthropic: соединение, запрос и перечень моделей.

Надстройка рядом с OpenAI-совместимым путём: точки входа (`lm_studio`,
`lm_chat`, `lm_models`) узнают этот клиент по типу и отдают его сюда. Здесь
то, чем Claude отличается: системный промпт отдельным параметром, отсутствие
temperature, блоки в ответе, отказ модели. Метки бед и проверка ответа
остаются общими у точек входа.

Правила разговора с Claude — уровень размышления, причины конца, отделение
системного промпта — общие с `adapters/claude_code`: модель та же, путь к ней
другой.
"""

import logging

import anthropic

from backend.provider_config import CLAUDE_HOST, LlmProviderConfig

_log = logging.getLogger(__name__)

# Адрес клиента — всегда корень, а не то, что набрано: SDK сам дописывает
# `/v1/...`, и набранный с `/v1` адрес давал бы `/v1/v1/messages` и 404,
# который человек прочёл бы как «модели нет».
_CLAUDE_URL = f"https://{CLAUDE_HOST}"

# Размышление расходует тот же предел, что и ответ. Пределы в `backend/llm`
# подобраны под локальную модель без размышления, и Claude обрывался бы на
# них, не дойдя до ответа. Запас прибавляется, а не подставляется: второй
# заход с поднятым пределом (`llm/answers.read_with_a_second_try`) иначе
# повторял бы первый слово в слово.
THINKING_ROOM = 16000

# Время и расход от уровня почти не зависят — их съедает запуск запроса и
# промпт на входе, — а вердикт от глубины размышления только выигрывает.
EFFORT = "high"

# Причина конца «модель отказалась отвечать». В словаре OpenAI её нет, и
# зовущий отличает её от обрыва и от ответа именно по этому слову.
REFUSED = "refusal"

# Причины конца в словаре OpenAI: по `length` зовущие решают про обрыв. Окно
# контекста, исчерпанное посреди ответа, — тот же обрыв. Общие с `claude_code`:
# Claude Code отдаёт причины конца словами API.
FINISH = {
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


def split_system(messages: list[dict[str, str]]) -> tuple[str, list[dict[str, str]]]:
    """Системный промпт отдельно от реплик — так его ждёт Claude на обоих путях.

    Одним правилом на API и на Claude Code: разъедься они, один и тот же
    промпт уходил бы к одной модели по-разному.
    """
    system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
    return system, [m for m in messages if m["role"] != "system"]


def _params(model: str, messages: list[dict[str, str]], max_tokens: int) -> dict:
    """Тело запроса: системные сообщения — в `system`, остальные — в `messages`."""
    system, turns = split_system(messages)
    params = {
        "model": model,
        "max_tokens": max_tokens + THINKING_ROOM,
        "messages": turns,
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": EFFORT},
    }
    if system:
        params["system"] = system
    return params


async def ask(client: ClaudeClient, model: str, request):
    """Спросить модель: текст и причина конца в словаре OpenAI.

    `request` — `lm_chat.ChatRequest`; тип не назван, потому что `lm_chat` сам
    зовёт этот модуль, и импорт навстречу замкнул бы круг.

    Ошибки SDK и `MissingKey` уходят наверх: метку им ставит `lm_chat`, одну на
    оба пути. Отказ модели — не ошибка, а ответ с причиной конца `REFUSED`.
    """
    _require_key(client)
    target = client if request.timeout is None else client.with_options(timeout=request.timeout)
    reply = await target.messages.create(
        **_params(model, request.messages, request.max_tokens)
    )
    text = "".join(block.text for block in reply.content if block.type == "text")
    return text, FINISH.get(reply.stop_reason, reply.stop_reason)


async def list_models(client: ClaudeClient) -> list[str]:
    """Модели, доступные ключу."""
    _require_key(client)
    return [one.id async for one in client.models.list()]


async def ping(client: ClaudeClient, model: str, text: str) -> None:
    """Пробный запрос с теми же параметрами, что у настоящих; беда — ошибкой SDK.

    Голый запрос прошёл бы и у модели, которая не принимает размышления или
    уровня, — кнопка проверки зеленела бы, а каждый настоящий запрос получал
    бы 400.
    """
    _require_key(client)
    await client.messages.create(
        **_params(model, [{"role": "user", "content": text}], max_tokens=16)
    )
