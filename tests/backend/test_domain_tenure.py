"""Сроки мест работы: период, полные годы, стаж по навыку."""

from datetime import date
from types import SimpleNamespace

from backend.domain.tenure import full_years, place_period, skill_years

TODAY = date(2026, 10, 9)


def _place(start, end=None):
    return SimpleNamespace(start_date=start, end_date=end)


def test_a_skill_counts_until_its_last_place_ends():
    """Навык с прошлой работы не растёт до сегодня."""
    places = [_place(date(2019, 1, 1), date(2020, 1, 1)), _place(date(2022, 1, 1), date(2023, 1, 1))]
    assert skill_years(places, TODAY) == 4


def test_a_skill_at_the_current_place_counts_until_today():
    assert skill_years([_place(date(2023, 10, 1))], TODAY) == 3


def test_a_start_after_the_end_is_not_negative_tenure():
    assert full_years(date(2026, 10, 10), TODAY) == 0


def test_a_closed_place_shows_both_months():
    assert place_period(_place(date(2019, 3, 1), date(2021, 11, 1))) == "03.2019 — 11.2021"
