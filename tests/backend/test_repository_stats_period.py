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


def test_today_counts_from_the_start_of_the_day():
    """«Сегодня» отсчитывается от начала суток, а не от часа назад.

    Разница видна: скользящий период в один день дал бы момент вчерашний,
    а начало суток — сегодняшний, с нулями во всех долях.
    """
    since = stats_period_since("today")

    now = datetime.now(timezone.utc)
    assert since.date() == now.date()
    assert (since.hour, since.minute, since.second, since.microsecond) == (0, 0, 0, 0)


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
