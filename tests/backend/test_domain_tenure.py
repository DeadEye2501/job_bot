"""Сроки мест работы: период, полные годы, стаж."""

from datetime import date
from types import SimpleNamespace

from backend.domain.tenure import full_years, place_period, worked_years
from tests.fakes.agent import TODAY


def _place(start, end=None):
    return SimpleNamespace(start_date=start, end_date=end)


def test_gaps_between_places_are_not_tenure():
    """Перерыв между местами стажем не считается."""
    places = [_place(date(2019, 1, 1), date(2019, 12, 31)), _place(date(2021, 1, 1), date(2021, 12, 31))]
    assert worked_years(places, TODAY) == 2


def test_overlapping_places_are_not_counted_twice():
    """Два места в одни месяцы — один срок, а не два."""
    places = [_place(date(2020, 1, 1), date(2021, 12, 31)), _place(date(2021, 1, 1), date(2022, 12, 31))]
    assert worked_years(places, TODAY) == 3


def test_a_place_inside_another_adds_nothing():
    places = [_place(date(2018, 1, 1), date(2021, 12, 31)), _place(date(2019, 1, 1), date(2019, 6, 30))]
    assert worked_years(places, TODAY) == 4


def test_time_after_the_last_place_is_not_tenure():
    """Закрытое место не растёт до сегодня."""
    assert worked_years([_place(date(2020, 1, 1), date(2022, 12, 31))], TODAY) == 3


def test_the_end_month_counts_whole_whatever_its_day():
    """Импорт резюме пишет конец первым числом месяца, окно — любым днём:
    «01.2020 — 12.2020» в обоих случаях — год."""
    assert worked_years([_place(date(2020, 1, 1), date(2020, 12, 1))], TODAY) == 1
    assert worked_years([_place(date(2020, 1, 1), date(2020, 12, 31))], TODAY) == 1


def test_an_unfinished_year_is_not_counted():
    assert worked_years([_place(date(2020, 1, 1), date(2021, 6, 30))], TODAY) == 1


def test_the_current_place_counts_until_today():
    assert worked_years([_place(date(2023, 10, 1))], TODAY) == 3


def test_an_end_in_the_future_counts_until_today():
    """Срок, который ещё не прошёл, стажем пока не стал."""
    assert worked_years([_place(date(2025, 11, 1), date(2030, 1, 1))], TODAY) == 1


def test_a_place_that_ends_before_it_starts_adds_nothing():
    places = [_place(date(2020, 1, 1), date(2020, 12, 31)), _place(date(2024, 5, 1), date(2024, 1, 1))]
    assert worked_years(places, TODAY) == 1


def test_a_place_starting_after_today_adds_nothing():
    assert worked_years([_place(date(2027, 1, 1))], TODAY) == 0


def test_a_date_after_the_end_gives_no_negative_years():
    assert full_years(date(2026, 10, 10), TODAY) == 0


def test_a_closed_place_shows_both_months():
    assert place_period(_place(date(2019, 3, 1), date(2021, 11, 1))) == "03.2019 — 11.2021"
