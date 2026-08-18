"""Следствия перевода кода периода в границу отсчёта.

Экран статистики предлагает пять периодов, и четыре из них дают границу «не
раньше чем», а пятый — отсутствие границы вовсе. «Сегодня» отличается от
остальных: считается от начала суток, а не от текущего часа минус что-то.
"""

from datetime import datetime, timedelta, timezone

import pytest

from backend.repository.stats_common import stats_period_since


@pytest.mark.parametrize(
    ("period", "days"),
    [
        pytest.param("week", 7, id="неделя"),
        pytest.param("month", 30, id="месяц"),
        pytest.param("quarter", 90, id="квартал"),
    ],
)
def test_a_rolling_period_counts_back_from_now(period, days):
    """Скользящий период отсчитывается назад от текущего момента.

    Границы проверяются с запасом в минуту с каждой стороны: между вызовом
    в тесте и вызовом внутри проверяемого кода проходит время, и точного
    равенства тут не бывает.
    """
    before = datetime.now(timezone.utc) - timedelta(days=days)

    since = stats_period_since(period)

    after = datetime.now(timezone.utc) - timedelta(days=days)
    assert before - timedelta(minutes=1) <= since <= after + timedelta(minutes=1)


def test_today_counts_from_the_local_start_of_the_day():
    """«Сегодня» отсчитывается от начала местных суток, а не от полуночи UTC.

    Полночь считает человек по своим часам, а не по всемирным. На поясе UTC+4
    отсчёт от полуночи UTC начинал бы «сегодня» в четыре утра: заведённое
    ночью в него не попадало бы, зато попадало бы вчерашнее с восьми вечера, и
    в два часа ночи экран показывал бы вчерашний день.

    Скользящий период в один день здесь тоже не годится: он дал бы момент
    вчерашний, а начало суток — сегодняшний.
    """
    since = stats_period_since("today")

    local = since.astimezone()
    assert local.date() == datetime.now().astimezone().date()
    assert (local.hour, local.minute, local.second, local.microsecond) == (0, 0, 0, 0)


@pytest.mark.parametrize(
    "period",
    ["all", "", "выдумка"],
    ids=["за всё время", "пусто", "незнакомый код"],
)
def test_everything_else_means_no_boundary(period):
    """Всё прочее означает отсутствие границы — считаем за всё время.

    Незнакомый код не отвергается нарочно: у экрана нет способа прислать
    его случайно, а падение статистики из-за опечатки в коде периода
    обошлось бы дороже, чем показ всей истории.
    """
    assert stats_period_since(period) is None
