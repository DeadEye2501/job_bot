"""Следствия, которые наблюдает тест `backend/telegram_time.py`.

Проверяется одно: метка, прошедшая через приведение, означает тот самый миг,
что и была. Сравнивать её с чем-то записанным дословно нельзя — ответ зависит
от пояса машины, — поэтому оба следствия наблюдаются кругом: метку возвращают
в миг и сверяют с исходным.
"""

from datetime import datetime, timedelta, timezone

from backend.telegram_time import tg_moment

# Произвольный миг, лишь бы не полночь и не круглый час: на них ошибка в
# полсуток или в час прошла бы незамеченной.
_TS = 1755500000.0


def test_a_naive_moment_from_telegram_keeps_its_instant():
    """Наивная метка от Telegram остаётся тем же мигом, а не сдвигается.

    Pyrogram отдаёт время сообщения наивным и по местным часам. Записанное как
    есть, оно уезжает от нашей шкалы ровно на пояс машины — и в одной колонке
    оказываются две шкалы, потому что своё время мы пишем в UTC.
    """
    got = tg_moment(datetime.fromtimestamp(_TS))

    assert got.tzinfo is None
    assert got.replace(tzinfo=timezone.utc).timestamp() == _TS


def test_a_moment_with_its_own_zone_is_brought_to_ours():
    """Метка со своим поясом приводится к нашей шкале, а не теряет пояс.

    Через то же приведение идёт и наше собственное время отправки — оно
    осведомлённое, в UTC. Просто снять у него пояс было бы верно только на
    машине в UTC.
    """
    moscow = timezone(timedelta(hours=3))

    got = tg_moment(datetime(2026, 8, 18, 15, 0, tzinfo=moscow))

    assert got == datetime(2026, 8, 18, 12, 0)


def test_no_moment_stays_no_moment():
    """Пустоты приведение не выдумывает: у сообщения может не быть времени."""
    assert tg_moment(None) is None
