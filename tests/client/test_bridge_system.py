"""Следствия домена «система»: чем занят бот и что показывает нижняя полоса.

Предмет — то, что видно всегда, на любом экране: режим работы, здоровье связи
и счёт непрочитанного. Журнал, снос данных и обращение к рабочему столу лежат
своими файлами — их открывают нарочно, а это видно постоянно.
"""

import logging

from tests.dbio import put
from tests.factories import at, hr_row, message_row


async def test_an_unknown_mode_is_refused_by_name(api, ask):
    """Незнакомый режим отбивают, назвав присланное.

    Режимов три, и приходят они строкой со страницы. Прими мост что попало —
    бот остался бы в прежнем режиме, а переключатель на экране показывал бы
    новый, и человек считал бы, что отправка включена.
    """
    answer = await ask(api.system.set_mode, "Полный вперёд")

    assert answer["fail"] == "denied"
    assert "Полный вперёд" in answer["detail"]


async def test_a_chosen_mode_comes_back_as_the_current_one(api, ask):
    """Выбранный режим возвращается тем же ответом, что рисует переключатель."""
    answer = await ask(api.system.set_mode, "DM Only")

    assert answer["ok"]["mode"] == "DM Only"


async def test_the_first_request_brings_the_whole_snapshot(api, ask):
    """Первый запрос приносит все три состояния сразу, одним ответом.

    Страница рисует нижнюю полосу целиком: здоровье, непрочитанное и режим.
    Приди одно без другого — полоса осталась бы наполовину пустой до первого
    своего опроса, то есть на секунды после открытия.
    """
    answer = await ask(api.system.initial)

    snapshot = answer["ok"]
    assert snapshot["health"]["db"] is True
    assert snapshot["unread"]["count"] == 0
    assert snapshot["mode"] == "Off"


async def test_the_page_can_ask_the_queue_what_is_new(api, ask, hub):
    """Страница спрашивает очередь тем же зовом, что и всё остальное.

    Без метода поверхности очередь была бы вещью в себе: копит, ждёт, отдаёт —
    и некому спросить. Живые события до страницы не дошли бы вовсе.
    """
    hub.events.add("ingestion_started")

    answer = await ask(api.system.events, 0)

    assert [one["kind"] for one in answer["ok"]["events"]] == ["ingestion_started"]


async def test_the_page_learns_that_the_queue_is_closed(api, ask, hub):
    """Закрытую очередь страница узнаёт по ответу, а не по молчанию.

    По этому признаку её цикл и останавливается. Не доедь он до страницы, та
    спрашивала бы мост, которого уже нет, до самой смерти окна.
    """
    hub.events.close()

    answer = await ask(api.system.events, 0)

    assert answer["ok"]["closed"] is True


async def test_a_broken_number_does_not_spin_the_page_against_the_bridge(api, ask, hub):
    """Испорченный номер не заводит страницу и мост в плотную петлю.

    Кольцо считает потерянным всё старше названного номера, и на отрицательном
    объявляет потерю даже пустое. Ответ тогда приходит мгновенно, номер не
    двигается — и цикл страницы крутится без передышки, съедая ядро.

    Очередь закрыта нарочно: живая на пустой вопрос ждёт свои двадцать пять
    секунд, и сторож жёг бы их на каждом прогоне.
    """
    hub.events.close()

    answer = await ask(api.system.events, -5)

    assert answer["ok"]["missed"] is False
    assert answer["ok"]["events"] == []


async def test_a_fresh_page_is_not_told_what_happened_before_it(api, ask, hub):
    """Страница, спросившая впервые, случившегося до себя не получает.

    Номера у неё ещё нет: она только что открылась или перезагрузилась. Отдай
    ей мост кольцо с начала — окно мигнуло бы плашками часовой давности как
    свежими: «обход закончен», «письмо пришло», «отклик отправлен» — всё разом
    и всё уже неправда.

    Очередь закрыта нарочно: живая на пустой вопрос ждёт свои двадцать пять
    секунд, и сторож жёг бы их на каждом прогоне.
    """
    hub.events.add("ingestion_finished")
    hub.events.add("unread_changed")
    hub.events.close()

    answer = await ask(api.system.events, None)

    assert answer["ok"]["events"] == []
    assert answer["ok"]["missed"] is False


async def test_a_deferred_model_probe_that_broke_leaves_its_trace(
    api, ask, runner, monkeypatch, caplog
):
    """Сорвавшаяся отложенная проба моделей не пропадает молча.

    Первую пробу лампочка ждёт, а все следующие уходят в сторону — ответа у
    них не спрашивает никто. Брось такая проба поломку, лампочка показывала бы
    прошлый ответ до самого закрытия окна, а следа не осталось бы нигде: ни в
    ответе, ни в журнале.
    """
    monkeypatch.setattr("client.bridge.system._MODEL_PROBE_INTERVAL_S", 0.0)
    await ask(api.system.health)

    def fall(*_args, **_kwargs):
        raise RuntimeError("поставщик отвалился")

    monkeypatch.setattr("client.bridge.system.health.model_alive", fall)

    with caplog.at_level(logging.ERROR, logger="client.bridge.system"):
        await ask(api.system.health)
        await runner.drain()

    # След пришпилен к своему источнику: `any` по всем записям прошёл бы и от
    # чужой трассировки, случившейся в том же тесте.
    assert [
        record.name for record in caplog.records if record.exc_info
    ] == ["client.bridge.system"]
    # И к самой беде: без этого сторож был бы зелен от любой трассировки, а
    # разбирать её человеку придётся именно по тексту броска.
    assert "поставщик отвалился" in caplog.text


async def test_the_last_unread_moment_reaches_the_window_with_its_zone(api, ask, session_factory):
    """Время последнего непрочитанного приходит окну с часовым поясом.

    Без пояса окно читает время как местное, и свежее сообщение в списке над
    полосой выглядит пришедшим несколько часов назад.
    """
    hr = hr_row(name="Анна")
    await put(session_factory, hr)
    await put(session_factory, message_row(hr_id=hr.id, is_incoming=True, read_at=None, sent_at=at(50)))

    answer = await ask(api.system.unread_chats)

    assert answer["ok"]["chats"][0]["last_at"] == at(50).isoformat() + "+00:00"



async def test_ready_from_the_window_reaches_the_bot(api, ask, with_bot):
    bot = with_bot()

    answer = await ask(api.system.human_done)

    assert answer == {"ok": {}} and bot.calls == [("human_done",)]


async def test_switching_off_cancels_nothing(api, ask, with_bot):
    """Режим решает, что запускает автоматика; начатое Off не трогает — его
    останавливает кнопка «Стоп»."""
    bot = with_bot()

    await ask(api.system.set_mode, "Off")

    assert [call for call in bot.calls if call[0].startswith("cancel")] == []
