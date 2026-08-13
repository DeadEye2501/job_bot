"""Следствия общей части моста: чем окну отвечают на любой запрос.

Предмет здесь один — дорога ответа, а не то, что по ней едет. Все сто пять
слотов отдают исход через один и тот же конверт и одну и ту же отправку, и
поведение этой дороги на отказе, на поломке и на отмене одинаково для всех.
"""

import asyncio
import json
import logging


async def test_the_answer_reaches_the_window_as_a_signal(main_api, watch):
    """Ответ доходит до окна отправкой, а не возвратом слота.

    Слот возвращает `None` сразу же — окно узнаёт исход только сигналом, и
    порвись эта дорога, интерфейс молчал бы, не показывая никакой ошибки.
    """
    caught = watch(main_api.vacancy_notes_saved)

    async def answered() -> str:
        return json.dumps({"ok": True, "notes": "готово"})

    main_api._dispatch(main_api.vacancy_notes_saved, answered())

    assert await caught.next() == {"ok": True, "notes": "готово"}


async def test_a_broken_coroutine_becomes_a_refusal_not_a_silence(
    main_api, watch, caplog
):
    """Поломка внутри работы превращается в отказ, а не теряется.

    Окно ждёт ответа на каждый запрос: пропади он — экран остался бы с
    крутящимся ожиданием навсегда. Имя породы и текст едут в окно, чтобы
    человеку было что показать, а трассировка — в журнал, чтобы было что
    читать потом.
    """
    caught = watch(main_api.vacancy_notes_saved)

    async def broken() -> str:
        raise RuntimeError("база не отвечает")

    with caplog.at_level(logging.ERROR, logger="client.bridge.answer"):
        main_api._dispatch(main_api.vacancy_notes_saved, broken())
        answer = await caught.next()

    assert answer == {"ok": False, "error": "RuntimeError: база не отвечает"}
    assert any(record.exc_info for record in caplog.records)


async def test_a_cancelled_request_says_nothing_at_all(main_api, watch):
    """Отменённая работа не отвечает вовсе.

    Отменяют при остановке приложения: обработчик в окне к этому мигу уже
    отвалился, и «работа отменена» уехало бы в умирающую страницу — человек
    увидел бы ошибку там, где просто закрыл окно.
    """
    caught = watch(main_api.vacancy_notes_saved)
    started = asyncio.Event()

    async def endless() -> str:
        started.set()
        await asyncio.sleep(3600)
        return ""

    coro = endless()
    main_api._dispatch(main_api.vacancy_notes_saved, coro)
    await started.wait()
    for task in asyncio.all_tasks():
        if task.get_coro() is coro:
            task.cancel()

    assert await caught.silent()


async def test_a_rejected_payload_never_lands_in_the_journal(main_api, watch, caplog):
    """Про неверную нагрузку пишут, чем она плоха, но не что в ней было.

    Через те же слоты ходят ключ доступа к модели, пароль и текст переписки.
    Запиши обработчик нагрузку целиком — секрет лёг бы в файл журнала, откуда
    его уже не вынуть.
    """
    caught = watch(main_api.vacancy_notes_saved)

    with caplog.at_level(logging.WARNING, logger="client.bridge.payload"):
        main_api.update_vacancy_notes(
            json.dumps({"vacancy_id": "sk-секретный-ключ", "notes": "тайна"})
        )

    answer = await caught.next()
    assert answer["ok"] is False
    written = "\n".join(record.getMessage() for record in caplog.records)
    assert "update_vacancy_notes" in written
    assert "sk-секретный-ключ" not in written
    assert "тайна" not in written


async def test_a_missing_field_is_named_in_the_journal(main_api, watch, caplog):
    """Про недостающее поле говорят, какое именно.

    Имя поля значением не является: оно написано нашей же формой, и без него
    запись сообщала бы только «нагрузка плоха» — по такой не понять, разошлись
    ли окно и мост в имени или человек оставил графу пустой.
    """
    caught = watch(main_api.vacancy_notes_saved)

    with caplog.at_level(logging.WARNING, logger="client.bridge.payload"):
        main_api.update_vacancy_notes(json.dumps({"notes": "без вакансии"}))

    assert (await caught.next())["ok"] is False
    written = "\n".join(record.getMessage() for record in caplog.records)
    assert "vacancy_id" in written
    assert "без вакансии" not in written
