"""Следствия запомненного замера скорости моделей.

Лампочка спрашивает поставщика только перечнем имён — время ответа модели по
нему не узнать. Настоящий вопрос задаётся один раз, на подключении, и его время
держится в ответе здоровья, пока связь жива: по нему экран настроек показывает
плашку, не дожидаясь нажатия «Проверить».
"""

import httpx

from tests.fakes.llm import CHAT, MODELS, models_response


SAVED_CHAT = {"chat": {"base_url": "http://provider.test", "api_key": "", "model": "qwen"}}


def models_say(monkeypatch, answers: list[bool]):
    """Лампочка слышит от поставщика по очереди то, что перечислено.

    Очередь двигает проба чата; эмбеддинги отвечают тем же, что чат на этой
    пробе: настроек у них в тесте нет, и мерить их нечего.
    """
    heard = iter(answers)
    now = {"alive": False}

    async def alive(_cfg, kind):
        if kind == "chat":
            now["alive"] = next(heard)
        return now["alive"]

    monkeypatch.setattr("client.bridge.system._MODEL_PROBE_INTERVAL_S", 0.0)
    monkeypatch.setattr("client.bridge.system.health.model_alive", alive)


def timed(monkeypatch, ms: int | None) -> list[str]:
    """Замер отвечает этим временем; отдаёт, о каких родах его спрашивали."""
    asked: list[str] = []

    async def speed(_cfg, kind):
        asked.append(kind)
        return ms

    monkeypatch.setattr("client.bridge.system._speed_of", speed)
    return asked


async def health_after_drain(api, ask, runner) -> dict:
    """Ответ здоровья после того, как отработало всё, что ушло в сторону."""
    await ask(api.system.health)
    await runner.drain()
    return (await ask(api.system.health))["ok"]


async def test_a_model_that_came_alive_is_timed_once(api, ask, runner, monkeypatch):
    """Ожившую модель меряют один раз, и время держится, пока она жива.

    Мерить на каждой пробе значило бы раз в минуту отнимать у бота очередь
    настоящим вопросом модели — ради числа, которое меняется редко.
    """
    await ask(api.settings.save, SAVED_CHAT)
    models_say(monkeypatch, [True] * 6)
    asked = timed(monkeypatch, 321)

    first = await health_after_drain(api, ask, runner)
    again = await health_after_drain(api, ask, runner)

    assert first["chat_ms"] == 321
    assert again["chat_ms"] == 321
    assert asked == ["chat"]


async def test_a_dropped_model_is_timed_anew_when_it_is_back(
    api, ask, runner, monkeypatch
):
    """После обрыва замер забывается, а вернувшуюся связь меряют заново.

    Время, снятое до обрыва, говорило бы о поставщике, которого, может быть,
    подняли уже на другой машине.
    """
    await ask(api.settings.save, SAVED_CHAT)
    models_say(monkeypatch, [True, True, False, False, True, True])
    asked = timed(monkeypatch, 321)

    await health_after_drain(api, ask, runner)
    dropped = await health_after_drain(api, ask, runner)
    await health_after_drain(api, ask, runner)

    assert dropped["chat_ms"] is None
    assert asked == ["chat", "chat"]


async def test_no_timing_while_a_round_runs(api, ask, runner, monkeypatch, with_bot):
    """Пока идёт прогон, модель не меряют: она занята разбором.

    Вопрос модели посреди прогона встал бы в очередь к ней рядом с работой
    бота, а параллельной работы модели быть не должно.
    """
    await ask(api.settings.save, SAVED_CHAT)
    bot = with_bot()
    bot.is_connected = True
    bot.is_running_round = True
    models_say(monkeypatch, [True] * 4)
    asked = timed(monkeypatch, 321)

    answer = await health_after_drain(api, ask, runner)

    assert answer["chat_ms"] is None
    assert asked == []


async def test_a_pressed_probe_of_the_saved_model_is_remembered(
    api, ask, runner, monkeypatch, provider_says
):
    """Нажатая проверка сохранённой модели и есть последний замер.

    Иначе плашка, показавшая свежее время, после ухода с экрана вернулась бы к
    старому — снятому при подключении.
    """
    await ask(api.settings.save, SAVED_CHAT)
    provider_says({
        MODELS: models_response("qwen"),
        CHAT: httpx.Response(
            200,
            json={"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]},
        ),
    })
    models_say(monkeypatch, [True] * 4)
    asked = timed(monkeypatch, 99999)

    probed = await ask(api.settings.probe_model, {"kind": "chat", **SAVED_CHAT["chat"]})
    answer = await health_after_drain(api, ask, runner)

    assert answer["chat_ms"] == probed["ok"]["latency_ms"]
    assert asked == []
