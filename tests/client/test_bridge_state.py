"""Следствия слотов состояния: чем занят бот и что показывает нижняя полоса.

Предмет — то, что видно всегда, на любом экране: режим работы, здоровье связи
и счёт непрочитанного. Журнал и настройки лежат своими файлами — их открывают
нарочно, а это видно постоянно.
"""


async def test_an_unknown_mode_is_refused_by_name(main_api, watch):
    """Незнакомый режим отбивают, назвав присланное.

    Режимов три, и приходят они строкой из окна. Прими мост что попало —
    бот остался бы в прежнем режиме, а переключатель на экране показывал бы
    новый, и человек считал бы, что отправка включена.
    """
    caught = watch(main_api.mode_changed)

    main_api.set_mode("Полный вперёд")

    answer = await caught.next()
    assert answer["ok"] is False
    assert "Полный вперёд" in answer["error"]


async def test_a_chosen_mode_comes_back_as_the_current_one(main_api, watch):
    """Выбранный режим возвращается тем же ответом, что рисует переключатель."""
    caught = watch(main_api.mode_changed)

    main_api.set_mode("DM Only")

    answer = await caught.next()
    assert answer["ok"] is True
    assert answer["mode"] == "DM Only"


async def test_the_first_request_brings_the_whole_snapshot(main_api, watch):
    """Первый запрос приносит все три состояния сразу, и все — удавшимися.

    Окно рисует нижнюю полосу целиком: здоровье, непрочитанное и режим.
    Приди одно без другого — полоса осталась бы наполовину пустой до первого
    срабатывания таймеров, то есть на секунды после открытия. Отказ тут
    равносилен пропаже: полоса нарисуется, но покажет неправду.
    """
    health = watch(main_api.health_changed)
    unread = watch(main_api.unread_changed)
    mode = watch(main_api.mode_changed)

    main_api.request_initial()

    assert (await health.next())["ok"] is True
    assert (await unread.next())["ok"] is True
    assert (await mode.next())["ok"] is True
