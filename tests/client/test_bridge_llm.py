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
    main_api, watch, provider_says
):
    """Проверка возвращает имя модели, которую проверяла.

    Моделей у провайдера много, а поле на экране одно, и правят его на ходу.
    Без эха имени ответ о работающей модели лёг бы рядом с только что
    введённым другим именем, и человек сохранил бы непроверенное.
    """
    caught = watch(main_api.llm_probe_done)
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

    main_api.request_llm_probe(
        json.dumps(
            {"kind": "chat", "base_url": "http://provider.test", "model": "qwen"}
        )
    )

    answer = await caught.next()
    assert answer["ok"] is True
    assert answer["model"] == "qwen"


async def test_a_probe_of_an_unknown_kind_is_refused_by_kind(main_api, watch):
    """Отказ проверки возвращается вместе с родом, который проверяли.

    Проверок на экране две — чат и векторы, — и обе отвечают одним сигналом.
    Без рода окно не поймёт, у какой из двух показывать ошибку.
    """
    caught = watch(main_api.llm_probe_done)

    main_api.request_llm_probe(
        json.dumps({"kind": "выдумка", "base_url": "http://provider.test", "model": "q"})
    )

    answer = await caught.next()
    assert answer["ok"] is False
    assert answer["kind"] == "выдумка"


async def test_a_broken_listing_answers_instead_of_raising(
    main_api, watch, provider_says
):
    """Недоступный провайдер не роняет запрос списка, а отвечает отказом.

    Список моделей просят при каждом открытии настроек, в том числе когда
    провайдер ещё не запущен. Поднимись тут исключение — экран настроек не
    открывался бы вовсе.
    """
    caught = watch(main_api.llm_models_listed)
    provider_says({MODELS: httpx.ConnectError("соединение отклонено")})

    main_api.request_llm_models(
        json.dumps({"kind": "chat", "base_url": "http://provider.test"})
    )

    answer = await caught.next()
    assert answer["ok"] is False
    assert answer["kind"] == "chat"


async def test_a_listing_without_an_address_stays_silent(main_api, watch):
    """Запрос списка без адреса остаётся без ответа вовсе.

    Поле адреса пусто, пока человек его не ввёл, а запрос уходит на каждое
    нажатие клавиши. Отвечай мост отказом — экран настроек мигал бы ошибкой
    на каждой букве.
    """
    caught = watch(main_api.llm_models_listed)

    main_api.request_llm_models(json.dumps({"kind": "chat", "base_url": ""}))

    assert await caught.silent()


async def test_a_saved_model_reaches_the_settings(wizard_api, main_api, watch):
    """Сохранённое мастером видно на экране настроек.

    Мастер и основное окно — разные объекты моста, и общее у них только
    записанное. Не доедь настройка, человек прошёл бы мастер и увидел пустые
    поля модели в настройках.
    """
    saved = watch(wizard_api.chat_save_done)
    shown = watch(main_api.system_settings_loaded)

    wizard_api.chat_save(
        json.dumps(
            {"base_url": "http://provider.test/", "api_key": "", "model": "qwen"}
        )
    )
    assert (await saved.next())["ok"] is True

    main_api.request_system_settings()
    assert (await shown.next())["chat"]["model"] == "qwen"
