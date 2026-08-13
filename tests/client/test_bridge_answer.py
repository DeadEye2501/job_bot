"""Следствия общей части моста: чем окну отвечают на любой запрос.

Предмет здесь один — дорога ответа, а не то, что по ней едет. Поведение на
отказе, на поломке и на отмене одинаково для всех, кто по ней ходит.

**Дорог сейчас две, и это переходное состояние.** Переехавшие домены отвечают
возвратом (`reply`), непереехавшие — сигналом (`_dispatch_json`). Вторая уходит
слайсом А2.9, и сторожа уйдут вместе с ней; расходятся дороги в одном —
поведении при отмене, и довод записан у `reply`.
"""

import asyncio
import json
import logging

from client.bridge.answer import reply


async def test_the_answer_reaches_the_window_as_a_signal(main_api, watch):
    """Ответ доходит до окна отправкой, а не возвратом слота.

    Слот возвращает `None` сразу же — окно узнаёт исход только сигналом, и
    порвись эта дорога, интерфейс молчал бы, не показывая никакой ошибки.
    """
    caught = watch(main_api.system_settings_loaded)

    async def answered() -> str:
        return json.dumps({"ok": True, "notes": "готово"})

    main_api._dispatch(main_api.system_settings_loaded, answered())

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
    caught = watch(main_api.system_settings_loaded)

    async def broken() -> str:
        raise RuntimeError("база не отвечает")

    with caplog.at_level(logging.ERROR, logger="client.bridge.answer"):
        main_api._dispatch(main_api.system_settings_loaded, broken())
        answer = await caught.next()

    assert answer == {"ok": False, "error": "RuntimeError: база не отвечает"}
    assert any(record.exc_info for record in caplog.records)


async def test_a_cancelled_request_says_nothing_at_all(main_api, watch):
    """Отменённая работа не отвечает вовсе.

    Отменяют при остановке приложения: обработчик в окне к этому мигу уже
    отвалился, и «работа отменена» уехало бы в умирающую страницу — человек
    увидел бы ошибку там, где просто закрыл окно.
    """
    caught = watch(main_api.system_settings_loaded)
    started = asyncio.Event()

    async def endless() -> str:
        started.set()
        await asyncio.sleep(3600)
        return ""

    coro = endless()
    main_api._dispatch(main_api.system_settings_loaded, coro)
    await started.wait()
    for task in asyncio.all_tasks():
        if task.get_coro() is coro:
            task.cancel()

    assert await caught.silent()


async def test_a_rejected_payload_never_lands_in_the_journal(api, ask, caplog):
    """Про неверную нагрузку пишут, чем она плоха, но не что в ней было.

    Через те же методы ходят ключ доступа к модели, пароль и текст переписки.
    Запиши обработчик нагрузку целиком — секрет лёг бы в файл журнала, откуда
    его уже не вынуть.
    """
    with caplog.at_level(logging.WARNING, logger="client.bridge.payload"):
        answer = await ask(
            api.vacancies.save_notes,
            {"vacancy_id": "sk-секретный-ключ", "notes": "тайна"},
        )

    assert answer["fail"] == "fields"
    written = "\n".join(record.getMessage() for record in caplog.records)
    assert "save_notes" in written
    assert "sk-секретный-ключ" not in written
    assert "тайна" not in written


async def test_a_missing_field_is_named_in_the_journal(api, ask, caplog):
    """Про недостающее поле говорят, какое именно.

    Имя поля значением не является: оно написано нашей же формой, и без него
    запись сообщала бы только «нагрузка плоха» — по такой не понять, разошлись
    ли окно и мост в имени или человек оставил графу пустой.
    """
    with caplog.at_level(logging.WARNING, logger="client.bridge.payload"):
        answer = await ask(api.vacancies.save_notes, {"notes": "без вакансии"})

    assert answer["fail"] == "fields"
    written = "\n".join(record.getMessage() for record in caplog.records)
    assert "vacancy_id" in written
    assert "без вакансии" not in written


async def test_a_broken_job_comes_back_named_on_the_new_road(runner, ask, caplog):
    """Поломка внутри работы возвращается зовущему отказом с причиной.

    Дорога возврата отвечает всегда, и беда едет тем же конвертом: имя породы и
    текст — окну, чтобы человеку было что показать, трассировка — в журнал,
    чтобы было что читать потом.
    """

    async def broken() -> str:
        raise RuntimeError("база не отвечает")

    with caplog.at_level(logging.ERROR, logger="client.bridge.answer"):
        answer = await ask(lambda: reply(runner, broken()))

    assert answer == {"fail": "broken", "detail": "RuntimeError: база не отвечает"}
    assert any(record.exc_info for record in caplog.records)


async def test_a_cancelled_job_comes_back_named_instead_of_silent(runner, ask):
    """Отменённая работа возвращается отказом, а не тишиной.

    Соседняя дорога на отмене молчит нарочно — там ответ уезжал в умирающую
    страницу. Здесь ответа ждёт зов, и молчание держало бы его до полного срока
    впустую.
    """
    started = asyncio.Event()

    async def endless() -> str:
        started.set()
        await asyncio.sleep(3600)
        return ""

    coro = endless()
    asked = asyncio.create_task(ask(lambda: reply(runner, coro)))
    await started.wait()
    for task in asyncio.all_tasks():
        if task.get_coro() is coro:
            task.cancel()

    assert await asked == {"fail": "cancelled"}


async def test_a_hanging_job_comes_back_by_its_own_deadline(
    runner, ask, monkeypatch
):
    """Зависшая работа отпускает зовущего по сроку, а не держит навсегда.

    Своего срока у канала нет вовсе: зависший зов оставил бы запись о себе до
    закрытия окна, а окно — крутящееся ожидание. Срок держит мост.
    """
    monkeypatch.setattr("client.bridge.answer.REPLY_SECONDS", 0.05)
    release = asyncio.Event()

    async def hangs() -> str:
        await release.wait()
        return "поздно"

    answer = await ask(lambda: reply(runner, hangs()))
    release.set()

    assert answer == {"fail": "timeout"}


async def test_the_jobs_own_deadline_is_not_mistaken_for_ours(runner, ask, caplog):
    """Свой срок работы приезжает поломкой, а не «мотор не успел».

    Внутренних сроков в мосте хватает — остановка бота, ожидание клиента, —
    и все они бьют тем же классом, что и наш. Спутав их, окно скажет «долго»
    там, где работа отказала, а в журнал не ляжет ничего: разбирать будет
    нечего.
    """

    async def impatient() -> str:
        raise TimeoutError("клиент не ответил за срок")

    with caplog.at_level(logging.ERROR, logger="client.bridge.answer"):
        answer = await ask(lambda: reply(runner, impatient()))

    assert answer["fail"] == "broken"
    assert "клиент не ответил за срок" in answer["detail"]
    assert any(record.exc_info for record in caplog.records)


async def test_a_dead_engine_answers_instead_of_throwing_at_the_channel(ask, caplog):
    """Отправка на закрытый мотор возвращается отказом, а не летит в канал.

    Мотор гасят при закрытии окна и при сносе данных, а запросы в этот миг ещё
    идут. Пролетев мимо конверта, беда ушла бы в pywebview, и страница получила
    бы не отказ, а поломку канала.
    """

    class Dead:
        def submit(self, coro):
            coro.close()
            raise RuntimeError("Event loop is closed")

    async def anything() -> str:
        return "не доедет"

    with caplog.at_level(logging.ERROR, logger="client.bridge.answer"):
        answer = await ask(lambda: reply(Dead(), anything()))

    assert answer["fail"] == "broken"
    assert "Event loop is closed" in answer["detail"]
