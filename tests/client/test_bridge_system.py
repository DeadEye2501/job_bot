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
