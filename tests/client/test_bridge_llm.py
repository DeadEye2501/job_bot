"""Следствия проверки языковой модели: что окно узнаёт, нажав «проверить».

Предмет — разговор с провайдером и его исход. Сам разговор ведёт
`adapters/lm_studio.py`, и его сторожат свои тесты; здесь смотрят на то, что
из этого доезжает до окна и что оно показывает человеку до сохранения.
"""

import asyncio
import logging
import time

import httpx
import pytest

from tests.fakes.llm import CHAT, MODELS, models_response


def _busy_provider(free: asyncio.Event):
    """Поставщик, отвечающий только пока событие взведено.

    Заготовки `tests.fakes.llm` тут не годятся: их обработчик отвечает сразу, а
    нужен молчащий — тот, что держит обращение неотвеченным, как держит его
    LM Studio, считающая чужой промпт.
    """

    def make(_cfg):
        async def answer(request):
            await free.wait()
            if request.url.path.endswith("/models"):
                return models_response("qwen")
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]},
            )

        return httpx.AsyncClient(
            base_url="http://provider.test", transport=httpx.MockTransport(answer)
        )

    return make


@pytest.fixture
def provider_says(monkeypatch):
    """Ставит на место провайдера подставного и отдаёт заготовленные ответы.

    Подменяется сборка соединения, а не сам мост: он зовёт её по имени модуля,
    и подделка садится туда же, куда сел бы настоящий клиент.
    """

    def _answer(routes) -> None:
        from tests.fakes.llm import provider

        monkeypatch.setattr(
            "adapters.lm_studio.make_client", lambda cfg: provider(routes)
        )

    return _answer


async def test_a_check_without_an_address_is_refused(api, ask):
    """Проверку без адреса и модели отбивают до похода в сеть.

    Форму проверяют на ходу, ещё не дописав адрес. Уйди запрос как есть, он
    ушёл бы в никуда и вернулся отказом соединения — из такого ответа не
    видно, что человек просто не дозаполнил поле.
    """
    answer = await ask(
        api.settings.probe_model, {"kind": "chat", "base_url": "", "model": ""}
    )

    assert answer["fail"] == "fields"
    assert "Заполните base_url и модель." in answer["detail"]


async def test_a_working_provider_names_the_models_it_has(api, ask, provider_says):
    """Опрошенный провайдер отдаёт свои имена моделей, а не пустоту.

    Имя модели человек вписывает руками, и подсказка — единственное, чем он
    сверяет написанное с тем, что у провайдера на самом деле поднято.
    """
    provider_says({MODELS: models_response("qwen", "llama")})

    answer = await ask(
        api.settings.list_models,
        {"kind": "chat", "base_url": "http://provider.test"},
    )

    assert "qwen" in answer["ok"]["models"]


async def test_a_silent_provider_is_told_apart_from_a_working_one(
    api, ask, provider_says
):
    """Молчащий провайдер отвечает отказом, а не пустым успехом.

    Проверку и нажимают затем, чтобы узнать это до первой вакансии. Ответь
    мост успехом — разбор объявлений молча не работал бы, а причина всплыла
    бы только в журнале.
    """
    provider_says({MODELS: httpx.ConnectError("соединение отклонено")})

    answer = await ask(
        api.settings.probe_model,
        {"kind": "chat", "base_url": "http://provider.test", "model": "qwen"},
    )

    assert answer["fail"] == "denied"


async def test_a_probe_answers_about_the_model_it_was_asked_about(
    api, ask, provider_says
):
    """Проверка возвращает имя модели, которую проверяла.

    Моделей у провайдера много, а поле на экране одно, и правят его на ходу.
    Без эха имени ответ о работающей модели лёг бы рядом с только что
    введённым другим именем, и человек сохранил бы непроверенное.
    """
    provider_says(
        {
            MODELS: models_response("qwen"),
            CHAT: httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]
                },
            ),
        }
    )

    answer = await ask(
        api.settings.probe_model,
        {"kind": "chat", "base_url": "http://provider.test", "model": "qwen"},
    )

    assert answer["ok"]["model"] == "qwen"


async def test_a_probe_of_an_unknown_kind_is_refused_by_kind(api, ask):
    """Отказ проверки возвращается вместе с родом, который проверяли.

    Проверок на экране две — чат и векторы, — и без рода окно не поймёт, у
    какой из двух показывать ошибку.
    """
    answer = await ask(
        api.settings.probe_model,
        {"kind": "выдумка", "base_url": "http://provider.test", "model": "q"},
    )

    assert answer["fail"] == "fields"
    assert answer["kind"] == "выдумка"


async def test_a_broken_listing_answers_instead_of_raising(api, ask, provider_says):
    """Недоступный провайдер не роняет запрос списка, а отвечает отказом.

    Список моделей просят при каждом открытии настроек, в том числе когда
    провайдер ещё не запущен. Поднимись тут исключение — экран настроек не
    открывался бы вовсе.
    """
    provider_says({MODELS: httpx.ConnectError("соединение отклонено")})

    answer = await ask(
        api.settings.list_models,
        {"kind": "chat", "base_url": "http://provider.test"},
    )

    assert answer["fail"] == "denied"
    assert answer["kind"] == "chat"


async def test_a_broken_listing_leaves_its_trace_in_the_log(api, ask, provider_says, caplog):
    """Сорвавшийся опрос имён оставляет в журнале трассировку, а не только текст.

    Человеку в плашку едет короткая фраза, и по ней не отличить неподнятого
    поставщика от оборванной сети или чужого ответа. Разбирать это можно
    только по журналу — другого следа у этой беды не остаётся вовсе.
    """
    provider_says({MODELS: httpx.ConnectError("соединение отклонено")})

    with caplog.at_level(logging.WARNING):
        await ask(
            api.settings.list_models,
            {"kind": "chat", "base_url": "http://provider.test"},
        )

    assert "Traceback (most recent call last)" in caplog.text
    assert "соединение отклонено" in caplog.text


async def test_a_listing_from_a_bad_address_is_refused_with_its_kind(api, ask):
    """Негодный адрес в запросе списка возвращается отказом со своим родом.

    Адрес набирают руками, и порт из букв — обычная опечатка, а не поломка
    приложения. Улети она мимо конверта, окно получило бы отказ без рода и
    погасило бы ожидание не у той из двух проверок.

    Стоит рядом с такой же проверкой у пробы связи нарочно: там это место было
    закрыто слайсом А2.8, а здесь осталась вторая половина.
    """
    answer = await ask(
        api.settings.list_models,
        {"kind": "chat", "base_url": "http://localhost:12ab"},
    )

    assert answer["fail"] == "denied"
    assert answer["kind"] == "chat"


async def test_a_listing_without_an_address_answers_with_nothing(api, ask):
    """Запрос списка без адреса отвечает пустым перечнем, а не отказом.

    Поле адреса пусто, пока человек его не ввёл, а запрос уходит на каждое
    нажатие клавиши. Отвечай мост отказом — экран настроек мигал бы ошибкой
    на каждой букве.
    """
    answer = await ask(api.settings.list_models, {"kind": "chat", "base_url": ""})

    assert answer["ok"]["models"] == []


async def test_an_answering_model_lights_the_lamp_green(
    api, ask, provider_says, runtime_settings
):
    """Живой поставщик со своей моделью зажигает лампочку зелёной.

    Здесь предмет — проводка: ответ доезжает от поставщика через `health` и
    домен «система» до слова в ответе моста. Чем именно лампочка спрашивает
    поставщика — предмет `tests/backend/test_health.py`, и там же сторожат,
    что сверх перечня она не стучится никуда.
    """
    provider_says({
        MODELS: models_response("qwen"),
        CHAT: httpx.Response(
            200,
            json={"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]},
        ),
    })
    await runtime_settings.set_chat(
        base_url="http://localhost:1234", api_key="", model="qwen"
    )

    answer = await ask(api.system.health)

    assert answer["ok"]["chat"] is True


async def test_the_lamp_answers_about_the_base_and_telegram_too(
    api, ask
):
    """Лампочка отвечает про базу и Telegram, а не только про модели.

    Три ответа окно рисует тремя разными огоньками. Пропади ключ или уедь
    он к соседу — человек чинил бы Telegram, глядя на погасшую базу.
    """
    answer = await ask(api.system.health)

    assert answer["ok"]["db"] is True
    assert answer["ok"]["tg"] is False


async def test_the_model_is_not_asked_again_within_the_minute(
    api, ask, provider_says, runtime_settings
):
    """Второй удар часов не идёт к поставщику заново, а показывает прошлый ответ.

    Ответ этот меняется редко: имя модели правят руками в настройках, а
    поставщика поднимают и гасят не каждую минуту. Часы бьют раз в пять
    секунд, и без разрежения лампочка спрашивала бы двадцать четыре раза в
    минуту на двоих то, что час стоит на месте.
    """
    provider_says({
        MODELS: models_response("qwen"),
        CHAT: httpx.Response(
            200,
            json={"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]},
        ),
    })
    await runtime_settings.set_chat(
        base_url="http://localhost:1234", api_key="", model="qwen"
    )

    first = await ask(api.system.health)
    assert first["ok"]["chat"] is True

    # Поставщик замолчал — но минута не прошла, и лампочка держит прошлый ответ.
    provider_says({MODELS: httpx.Response(500, text="упал")})
    again = await ask(api.system.health)

    assert again["ok"]["chat"] is True


async def test_a_slow_provider_is_not_asked_twice_at_once(
    api, ask, provider_says, runtime_settings
):
    """Пока проба в полёте, вторая не заводится.

    Часы бьют раз в пять секунд, а адрес, который глотает пакеты — задремавшая
    машина, закрытый межсетевым экраном порт, — не отказывает, а молчит до
    срока в три минуты. Без этого заслона каждый удар заводил бы новую пару
    ожиданий поверх незакончившихся: тридцать шесть штук за те же три минуты.
    """
    provider_says({
        MODELS: models_response("qwen"),
        CHAT: httpx.Response(
            200,
            json={"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]},
        ),
    })
    await runtime_settings.set_chat(
        base_url="http://localhost:1234", api_key="", model="qwen"
    )

    api.system._models_in_flight = True
    answer = await ask(api.system.health)

    assert answer["ok"]["chat"] is False


async def test_a_busy_provider_does_not_put_out_the_lamp(
    api, ask, runner, monkeypatch, runtime_settings
):
    """Медлящий поставщик держит прошлый ответ, а не гасит лампочку.

    Отчего он замолчал — по журналу не восстановить, и заслон стоит не
    против названной причины, а против самого молчания: окно
    на погасшую лампочку переводит бота в Off, обрывая его же обход на
    полуслове, а недоразобранная вакансия получает Not Fit по несостоявшемуся
    запросу, а не по своему содержанию.
    """
    free = asyncio.Event()
    free.set()
    monkeypatch.setattr("adapters.lm_studio.make_client", _busy_provider(free))
    await runtime_settings.set_chat(
        base_url="http://localhost:1234", api_key="", model="qwen"
    )
    lit = await ask(api.system.health)
    assert lit["ok"]["chat"] is True

    free.clear()
    # Минута прошла — пора спрашивать заново, и на этот раз поставщик занят.
    # Час назад, а не «никогда»: «никогда» — это первая проба, и её ждут.
    api.system._models_probed_at = time.monotonic() - 3600

    answer = await ask(api.system.health)

    assert answer["ok"]["chat"] is True
    free.set()
    await runner.drain()


async def test_a_bad_address_is_refused_with_its_kind(api, ask):
    """Негодный адрес поставщика возвращается отказом со своим родом.

    Проверок на экране две, и род — единственное, чем окно их различает: без
    него ожидание погаснет не у той. Адрес человек набирает руками, и порт из
    букв — обычная опечатка, а не поломка приложения.

    Красной фазы у этого сторожа не было: он дописан по находке ревью вместе с
    правкой, и доверие заслужит итоговым проходом.
    """
    answer = await ask(
        api.settings.probe_model,
        {"kind": "chat", "base_url": "http://localhost:12ab", "model": "qwen"},
    )

    assert answer["fail"] == "denied"
    assert answer["kind"] == "chat"
