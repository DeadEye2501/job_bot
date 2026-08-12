"""Следствия, которые наблюдает оповещение окна `backend/notify.py`.

Семь мест полагаются на то, что поломка подписчика не роняет работу, ради
которой всё затевалось. Через них это и проверялось: сними перехват внутри
`fire` — покраснеет много чужих проверок, и ни одна не скажет, что сломано
именно оповещение. Здесь предмет назван прямо.
"""

import logging

from backend.notify import fire


def test_a_broken_subscriber_leaves_a_traceback_in_the_log(caplog):
    """Поломка подписчика наружу не выходит, а оседает трассировкой в журнале.

    Зовущий продолжает работу: оповещение красит окно, и менять записанную
    строку на неотрисованный список было бы обменом важного на украшение.
    Отдельной проверки на «не выходит» нет нарочно — вышедшая поломка
    уронила бы этот же тест, а больше о ней сказать нечего. Сказать есть о
    журнале: снаружи проглоченная поломка от исправной работы не отличается
    ничем, и разбирать, почему окно перестало обновляться, придётся по нему.
    """

    def breaks(_):
        raise RuntimeError("окно упало")

    with caplog.at_level(logging.ERROR, logger="backend.notify"):
        fire(breaks, "on_new_message", 7)

    assert [
        record.exc_info is not None
        for record in caplog.records
        if record.name == "backend.notify"
    ] == [True]


def test_a_working_subscriber_gets_every_argument():
    """Исправному подписчику доходят все доводы, и в том же порядке.

    Окно читает их позиционно: разъехавшийся порядок показал бы переписку
    не того человека, а лишний или потерянный довод уронил бы подписчика —
    и поломка ушла бы в журнал, где её никто не ждёт.
    """
    heard: list[tuple] = []

    fire(lambda *args: heard.append(args), "on_hr_read", 7, 42)

    assert heard == [(7, 42)]


def test_no_subscriber_is_not_a_mishap(caplog):
    """Отсутствие подписчика бедой не считается и следа не оставляет.

    Окна может не быть вовсе — бот работает и из командной строки, — и
    жалоба на каждое событие засыпала бы журнал.
    """
    with caplog.at_level(logging.DEBUG, logger="backend.notify"):
        fire(None, "on_new_message", 7)

    assert [record for record in caplog.records if record.name == "backend.notify"] == []
