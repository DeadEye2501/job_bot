"""Следствия проверки языковой модели: что окно узнаёт, нажав «проверить».

Предмет — разговор с провайдером и его исход. Сам разговор ведёт
`adapters/lm_studio.py`, и его сторожат свои тесты; здесь смотрят на то, что
из этого доезжает до окна и что оно показывает человеку до сохранения.
"""

import json

import httpx
import pytest

from tests.fakes.llm import CHAT, MODELS, models_response


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


async def test_a_check_without_an_address_is_refused(wizard_api, watch):
    """Проверку без адреса и модели отбивают до похода в сеть.

    Форму проверяют на ходу, ещё не дописав адрес. Уйди запрос как есть, он
    ушёл бы в никуда и вернулся отказом соединения — из такого ответа не
    видно, что человек просто не дозаполнил поле.
    """
    caught = watch(wizard_api.chat_check_done)

    wizard_api.chat_check(json.dumps({"base_url": "", "model": ""}))

    answer = await caught.next()
    assert answer["ok"] is False
    assert answer["error"] == "Заполните base_url и модель."


async def test_a_working_model_answers_with_what_it_can_do(
    wizard_api, watch, provider_says
):
    """Удавшаяся проверка приносит и объяснение, и список моделей.

    Список нужен тут же: имя модели человек вписывает руками, и опечатку в
    нём видно только рядом с тем, что провайдер на самом деле умеет.
    """
    caught = watch(wizard_api.chat_check_done)
    provider_says(
        {
            MODELS: models_response("qwen", "llama"),
            CHAT: httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]
                },
            ),
        }
    )

    wizard_api.chat_check(
        json.dumps({"base_url": "http://provider.test", "model": "qwen"})
    )

    answer = await caught.next()
    assert answer["ok"] is True
    assert "qwen" in answer["models"]


async def test_a_silent_provider_is_told_apart_from_a_working_one(
    wizard_api, watch, provider_says
):
    """Молчащий провайдер отвечает отказом, а не пустым успехом.

    Проверку и нажимают затем, чтобы узнать это до первой вакансии. Ответь
    мост успехом — разбор объявлений молча не работал бы, а причина всплыла
    бы только в журнале.
    """
    caught = watch(wizard_api.chat_check_done)
    provider_says({MODELS: httpx.ConnectError("соединение отклонено")})

    wizard_api.chat_check(
        json.dumps({"base_url": "http://provider.test", "model": "qwen"})
    )

    assert (await caught.next())["ok"] is False


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


async def test_a_listing_without_an_address_answers_with_nothing(api, ask):
    """Запрос списка без адреса отвечает пустым перечнем, а не отказом.

    Поле адреса пусто, пока человек его не ввёл, а запрос уходит на каждое
    нажатие клавиши. Отвечай мост отказом — экран настроек мигал бы ошибкой
    на каждой букве.
    """
    answer = await ask(api.settings.list_models, {"kind": "chat", "base_url": ""})

    assert answer["ok"]["models"] == []


async def test_a_saved_model_reaches_the_settings(wizard_api, watch, api, ask):
    """Сохранённое мастером видно на экране настроек.

    Мастер и основное окно — разные объекты моста, и общее у них только
    записанное. Не доедь настройка, человек прошёл бы мастер и увидел пустые
    поля модели в настройках.
    """
    saved = watch(wizard_api.chat_save_done)

    wizard_api.chat_save(
        json.dumps(
            {"base_url": "http://provider.test/", "api_key": "", "model": "qwen"}
        )
    )
    assert (await saved.next())["ok"] is True

    answer = await ask(api.settings.get)
    assert answer["ok"]["chat"]["model"] == "qwen"


async def test_a_listed_but_silent_model_lights_the_lamp_red(
    main_api, watch, provider_says, runtime_settings
):
    """Лампочка в шапке гаснет от той же беды, что и кнопка проверки.

    Модель числится у провайдера и не отвечает — из-за нехватки памяти или
    чужой занятости. Смотри лампочка только перечень имён, человек видел бы
    зелёное в шапке и красное в настройках на одном и том же наборе, и не
    понял бы, чему верить.
    """
    caught = watch(main_api.health_changed)
    provider_says({
        MODELS: models_response("qwen"),
        CHAT: httpx.Response(500, text="модель выгружена"),
    })
    await runtime_settings.set_chat(
        base_url="http://localhost:1234", api_key="", model="qwen"
    )

    main_api.request_initial()

    assert (await caught.next())["chat"] is False


async def test_saving_a_provider_without_a_model_is_refused(wizard_api, watch):
    """Пустую модель не сохраняют молча.

    Сохранённая пустота выглядит как настроенный поставщик: экран показывает
    заполненный адрес, а первый же разбор вакансии падает на пустом имени
    модели — и ищут беду где угодно, только не в мастере.
    """
    caught = watch(wizard_api.chat_save_done)

    wizard_api.chat_save(json.dumps({"base_url": "http://localhost:1234", "model": ""}))

    answer = await caught.next()
    assert answer["ok"] is False
    assert answer["error"] == "Заполните base_url и модель."


async def test_an_answering_model_lights_the_lamp_green(
    main_api, watch, provider_says, runtime_settings
):
    """Отвечающая модель зажигает лампочку зелёной.

    Стоит рядом с проверкой молчащей нарочно: та одна была бы зелена и на
    лампочке, погасшей навсегда, — а погасшая насовсем отправляет человека
    чинить то, что работает.
    """
    caught = watch(main_api.health_changed)
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

    main_api.request_initial()

    assert (await caught.next())["chat"] is True


async def test_the_lamp_answers_about_the_base_and_telegram_too(
    main_api, watch, session_factory
):
    """Лампочка отвечает про базу и Telegram, а не только про модели.

    Три ответа окно рисует тремя разными огоньками. Пропади ключ или уедь
    он к соседу — человек чинил бы Telegram, глядя на погасшую базу.
    """
    caught = watch(main_api.health_changed)

    main_api.request_initial()

    answer = await caught.next()
    assert answer["db"] is True
    assert answer["tg"] is False


async def test_the_model_is_not_asked_again_within_the_minute(
    main_api, watch, provider_says, runtime_settings
):
    """Второй удар часов не идёт к модели заново, а показывает прошлый ответ.

    Вопрос к модели — настоящая генерация: спрашивай его каждые пять секунд,
    и модель не выгрузится из памяти никогда, а неподнятый поставщик завалит
    журнал трассировками ровно тогда, когда человек ещё заполняет мастер.
    """
    caught = watch(main_api.health_changed)
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

    main_api.request_initial()
    assert (await caught.next())["chat"] is True

    # Поставщик замолчал — но минута не прошла, и лампочка держит прошлый ответ.
    provider_says({MODELS: httpx.Response(500, text="упал")})
    main_api.request_initial()

    assert (await caught.next())["chat"] is True


async def test_a_slow_provider_is_not_asked_twice_at_once(
    main_api, watch, provider_says, runtime_settings
):
    """Пока проба в полёте, вторая не заводится.

    Часы бьют раз в пять секунд, а поставщик отвечает и минутами: LM Studio
    подгружает модель. Без этого заслона каждый удар заводил бы новую пару
    настоящих генераций поверх незакончившихся, и модель уже никогда не
    выгрузилась бы из памяти.
    """
    caught = watch(main_api.health_changed)
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

    main_api._models_in_flight = True
    main_api.request_initial()

    assert (await caught.next())["chat"] is False


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
