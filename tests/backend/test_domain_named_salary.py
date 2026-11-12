"""Отсев по зарплате и названная сумма — по вилке вакансии и зарплате анкеты."""

import pytest

from backend.domain.named_salary import (
    Offer,
    Pay,
    SalaryAsk,
    judge_salary,
    offer_of,
    offer_period,
)
from backend.models import SalaryPeriod

MONTH, HOUR, YEAR = SalaryPeriod.MONTH, SalaryPeriod.HOUR, SalaryPeriod.YEAR
RATES = {"$": 1.0, "₽": 80.0, "€": 0.9}


def ask(minimum=None, desired=None, currency="$", period=MONTH) -> SalaryAsk:
    return SalaryAsk(minimum=minimum, desired=desired, currency=currency, period=period)


def offer(low=None, high=None, currency="$", period=MONTH) -> Offer:
    return Offer(low=low, high=high, currency=currency, period=period)


def test_a_ceiling_below_the_minimum_refuses():
    verdict = judge_salary(offer(1000, 1500), ask(minimum=2000, desired=4000), RATES)
    assert verdict.refusal is not None and "1500" in verdict.refusal


def test_a_refused_ceiling_is_still_named():
    """Вакансию, заведённую вручную, отказ не отсеивает — откликатель называет верх."""
    verdict = judge_salary(offer(1000, 1500), ask(minimum=2000, desired=4000), RATES)
    assert verdict.pay == Pay(1500, "$", MONTH)


def test_a_ceiling_at_or_above_the_minimum_is_named():
    verdict = judge_salary(offer(1000, 1500), ask(minimum=1200, desired=4000), RATES)
    assert verdict.refusal is None
    assert verdict.pay == Pay(1500, "$", MONTH)


def test_the_ceiling_is_named_even_far_above_the_desired():
    assert judge_salary(offer(6000, 8000), ask(desired=4000), RATES).pay == Pay(8000, "$", MONTH)


def test_the_floor_does_not_matter_when_a_ceiling_is_named():
    with_floor = judge_salary(offer(100, 3000), ask(minimum=2000, desired=4000), RATES)
    without = judge_salary(offer(None, 3000), ask(minimum=2000, desired=4000), RATES)
    assert with_floor == without


@pytest.mark.parametrize(("floor", "named"), [(1000, 4000), (5000, 5000)])
def test_a_floor_alone_names_the_larger_of_it_and_the_desired(floor, named):
    verdict = judge_salary(offer(floor, None), ask(minimum=4500, desired=4000), RATES)
    assert verdict.refusal is None
    assert verdict.pay.amount == named


def test_a_floor_alone_without_a_desired_names_the_floor():
    assert judge_salary(offer(1000, None), ask(), RATES).pay == Pay(1000, "$", MONTH)


def test_no_salary_names_the_desired():
    verdict = judge_salary(offer(None, None, None, None), ask(minimum=2000, desired=4000), RATES)
    assert verdict == judge_salary(offer(None, None, None, None), ask(minimum=2000, desired=4000), {})
    assert verdict.refusal is None and verdict.pay == Pay(4000, "$", MONTH)


def test_nothing_to_name_without_a_desired():
    assert judge_salary(offer(None, None, None, None), ask(), RATES).pay is None


def test_a_range_without_a_currency_counts_as_no_salary():
    verdict = judge_salary(offer(1000, 1500, currency=None), ask(minimum=2000, desired=4000), RATES)
    assert verdict.refusal is None and verdict.pay == Pay(4000, "$", MONTH)


def test_a_range_without_a_period_counts_as_no_salary():
    """Так лежат вакансии, разобранные до появления периода: «$30/hr» там — 30."""
    verdict = judge_salary(offer(None, 30, period=None), ask(minimum=2000, desired=4000), RATES)
    assert verdict.refusal is None and verdict.pay == Pay(4000, "$", MONTH)


def test_a_foreign_ceiling_is_named_in_the_ask_currency_rounded():
    # 161 069 ₽ по 80 — 2013.36 $: две значащие цифры.
    verdict = judge_salary(offer(None, 161069, "₽"), ask(desired=1000), RATES)
    assert verdict.pay == Pay(2000, "$", MONTH)


def test_rounding_takes_the_half_up():
    # 100 000 ₽ по 80 — 1250 $ ровно.
    assert judge_salary(offer(None, 100000, "₽"), ask(desired=1000), RATES).pay.amount == 1300


def test_a_yearly_ceiling_is_named_monthly():
    assert judge_salary(offer(None, 60000, period=YEAR), ask(desired=1000), RATES).pay == Pay(5000, "$", MONTH)


def test_a_monthly_ceiling_is_named_hourly():
    # 1500 $ в месяц на 168 часов — 8.93 $ в час.
    verdict = judge_salary(offer(None, 1500), ask(desired=5, period=HOUR), RATES)
    assert verdict.pay == Pay(8.9, "$", HOUR)


def test_a_ceiling_in_the_ask_units_is_named_as_is():
    assert judge_salary(offer(None, 2013), ask(desired=1000), {}).pay == Pay(2013, "$", MONTH)


def test_the_refusal_compares_the_exact_amount_not_the_rounded():
    # 161 069 ₽ — 2013.36 $; округлённое 2000 было бы ниже минимальной 2010.
    verdict = judge_salary(offer(None, 161069, "₽"), ask(minimum=2010, desired=1000), RATES)
    assert verdict.refusal is None


def test_the_refusal_names_the_period_of_the_offer():
    verdict = judge_salary(offer(None, 5, period=HOUR), ask(minimum=2000), RATES)
    assert "в час" in verdict.refusal


def test_no_ask_means_no_refusal_and_nothing_to_name():
    verdict = judge_salary(offer(None, None, None, None), SalaryAsk(), RATES)
    assert verdict.refusal is None and verdict.pay is None


@pytest.mark.parametrize(
    ("low", "high", "period", "expected"),
    [(3000, None, None, MONTH), (None, None, YEAR, None), (None, 30, HOUR, HOUR)],
)
def test_offer_period(low, high, period, expected):
    assert offer_period(low, high, period) is expected


def test_offer_of_takes_the_string_currency_over_the_model():
    assert offer_of("$3000-5000", None, "₽") == Offer(3000, 5000, "$", MONTH)


def test_offer_of_falls_back_to_the_model_currency():
    assert offer_of("150 000 - 200 000", YEAR, "₽") == Offer(150000, 200000, "₽", YEAR)
