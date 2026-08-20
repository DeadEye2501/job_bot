"""Договор копилки отложенного разбора: пачки, таймеры и начавшие.

Одному человеку — одна пачка писем и один таймер над ней. Дотикав, таймер
забирает пачку себе и переходит в начавшие: отменять его с этого мига уже
нельзя, пачки в копилке больше нет и терять её некуда. Всё это держалось
четырьмя полями конвейера и договорённостью между функциями; здесь оно одно
целое, и проверяется тоже целым.
"""

import asyncio

from backend.flows.dm_debounce import DmDebounce


def _letter(tg_msg_id: int, text: str) -> dict:
    return {"vacancy_id": 1, "msg_id": tg_msg_id, "tg_msg_id": tg_msg_id,
            "text": text}


def test_a_remembered_letter_waits_in_its_burst():
    """Записанное письмо лежит в пачке своего человека."""
    bag = DmDebounce(cap=50, slots=2)

    bag.remember(7, _letter(1, "здравствуйте"))

    assert [i["text"] for i in bag.bursts.get(7, [])] == ["здравствуйте"]


def test_two_correspondents_keep_their_bursts_apart():
    """Пачки двух людей не смешиваются: разбор идёт по каждому свой."""
    bag = DmDebounce(cap=50, slots=2)

    bag.remember(7, _letter(1, "первый"))
    bag.remember(8, _letter(2, "второй"))

    assert [i["text"] for i in bag.bursts.get(7, [])] == ["первый"]
    assert [i["text"] for i in bag.bursts.get(8, [])] == ["второй"]


def test_an_overlong_burst_keeps_only_its_tail():
    """Зациклившийся человек не раздувает память: остаётся хвост пачки.

    Число выброшенных копилка отдаёт наверх — сказать о нём в журнал может
    только зовущий, здесь имени человека нет.
    """
    bag = DmDebounce(cap=2, slots=2)

    dropped = [bag.remember(7, _letter(n, str(n))) for n in (1, 2, 3, 4)]

    assert dropped == [0, 0, 1, 1]
    assert [i["text"] for i in bag.bursts.get(7, [])] == ["3", "4"]


def test_an_edited_letter_is_updated_in_place():
    """Правка догоняет письмо в пачке: разбор увидит свежий текст."""
    bag = DmDebounce(cap=50, slots=2)
    bag.remember(7, _letter(1, "было"))
    bag.remember(7, _letter(2, "второе"))

    bag.retext(7, 1, "стало")

    assert [i["text"] for i in bag.bursts.get(7, [])] == ["стало", "второе"]


def test_an_edit_of_something_not_remembered_changes_nothing():
    """Правка письма, которого в копилке нет, ничего не трогает."""
    bag = DmDebounce(cap=50, slots=2)
    bag.remember(7, _letter(1, "было"))

    bag.retext(7, 99, "чужое")
    bag.retext(8, 1, "чужое")

    assert [i["text"] for i in bag.bursts.get(7, [])] == ["было"]


def test_removing_a_letter_that_is_not_there_changes_nothing():
    """Удаление того, чего в пачке нет, ничего не меняет и не падает.

    Оповещение об удалении приходит на любое письмо переписки, а ждёт
    разбора только свежее — чужой человек и чужой номер здесь обычное дело.
    """
    bag = DmDebounce(cap=50, slots=2)
    bag.remember(7, _letter(1, "первое"))

    bag.forget(8, 1)
    bag.forget(7, 99)

    assert [i["text"] for i in bag.bursts.get(7, [])] == ["первое"]


def test_a_deleted_letter_leaves_the_burst():
    """Удалённое письмо выпадает из пачки и в разбор не идёт."""
    bag = DmDebounce(cap=50, slots=2)
    bag.remember(7, _letter(1, "первое"))
    bag.remember(7, _letter(2, "второе"))

    bag.forget(7, 1)

    assert [i["text"] for i in bag.bursts.get(7, [])] == ["второе"]


def test_removing_the_last_letter_drops_the_burst_itself():
    """Пустая пачка не остаётся: разбирать по ней нечего."""
    bag = DmDebounce(cap=50, slots=2)
    bag.remember(7, _letter(1, "одно"))

    bag.forget(7, 1)

    assert bag.waiting() == []


def test_a_taken_burst_is_gone_from_the_bag():
    """Забранная пачка из копилки уходит: второй раз её не разберут."""
    bag = DmDebounce(cap=50, slots=2)
    bag.remember(7, _letter(1, "одно"))

    taken = bag.take(7)

    assert [i["text"] for i in taken] == ["одно"]
    assert bag.take(7) == []


def test_a_dropped_burst_is_gone():
    """Брошенная пачка не разбирается вовсе — так уходит пачка из чёрного."""
    bag = DmDebounce(cap=50, slots=2)
    bag.remember(7, _letter(1, "одно"))

    bag.drop(7)

    assert bag.waiting() == []


def test_only_the_filled_bursts_are_waiting():
    """В ожидающих числятся только те, у кого есть что разбирать."""
    bag = DmDebounce(cap=50, slots=2)
    bag.remember(7, _letter(1, "одно"))
    bag.remember(8, _letter(2, "два"))
    bag.take(8)

    assert bag.waiting() == [7]


async def test_a_second_timer_cancels_the_first():
    """Свежее письмо отодвигает разбор: прежний таймер гасится.

    Иначе разбор ушёл бы в модель, не дождавшись мысли, дописанной вторым
    сообщением, — а платят за каждое обращение.
    """
    bag = DmDebounce(cap=50, slots=2)
    first = asyncio.create_task(asyncio.sleep(30))
    bag.arm(7, first)

    second = asyncio.create_task(asyncio.sleep(30))
    bag.arm(7, second)
    await asyncio.sleep(0)

    assert first.cancelled()
    assert list(bag.timers) == [7]
    second.cancel()


async def test_the_owner_of_the_hour_takes_its_timer_off():
    """Дотикавший таймер снимает себя с человека и получает добро на разбор."""
    bag = DmDebounce(cap=50, slots=2)
    task = asyncio.create_task(asyncio.sleep(30))
    bag.arm(7, task)

    assert bag.claim(7, task) is True
    assert bag.timers == {}
    task.cancel()


async def test_a_superseded_timer_gets_no_claim():
    """Отменённый и опоздавший таймер разбор не начинает.

    Начни он его — вынул бы пачку из-под свежего таймера, и тот разобрал бы
    пустоту, а накопленное пропало бы молча.
    """
    bag = DmDebounce(cap=50, slots=2)
    old = asyncio.create_task(asyncio.sleep(30))
    new = asyncio.create_task(asyncio.sleep(30))
    bag.arm(7, old)
    bag.arm(7, new)

    assert bag.claim(7, old) is False
    assert list(bag.timers) == [7]
    new.cancel()


async def test_a_started_reading_is_counted_apart_from_timers():
    """Начавшийся разбор числится отдельно от спящих таймеров.

    Спящих остановка отменяет, начавшихся — дожидается: пачку они уже вынули,
    и отмена потеряла бы её насовсем.
    """
    bag = DmDebounce(cap=50, slots=2)
    task = asyncio.create_task(asyncio.sleep(30))

    bag.begin(task)
    assert bag.busy() == [task]

    bag.end(task)
    assert bag.busy() == []
    task.cancel()


async def test_stopping_cancels_the_sleeping_timers():
    """Остановка гасит спящие таймеры и отдаёт их — чтобы дождаться."""
    bag = DmDebounce(cap=50, slots=2)
    task = asyncio.create_task(asyncio.sleep(30))
    bag.arm(7, task)

    cancelled = bag.cancel_timers()
    await asyncio.sleep(0)

    assert cancelled == [task]
    assert task.cancelled()
