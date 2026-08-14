"""Следствия домена «система»: чем занят бот и что показывает нижняя полоса.

Предмет — то, что видно всегда, на любом экране: режим работы, здоровье связи
и счёт непрочитанного. Журнал, снос данных и обращение к рабочему столу лежат
своими файлами — их открывают нарочно, а это видно постоянно.
"""


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
