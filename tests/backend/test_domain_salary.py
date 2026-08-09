"""Следствия, которые наблюдают тесты `backend/domain/salary.py`.

Разбор ничего не пересчитывает: из строки достаётся число, как оно в ней
записано, и валюта, если названа. Приведение к одной валюте было бы враньём —
курс в объявлении не указан, а отбор в списке идёт по написанному числу.

Проверяется не точность подсчёта, а то, что число не разваливается на
разрядах, суффикс тысяч раскрывается, а мусор не превращается в зарплату.
"""

import pytest

from backend.domain.salary import parse_salary
from backend.models import Currency


@pytest.mark.parametrize("raw", [None, "", "   ", "—"])
def test_nothing_is_extracted_from_a_blank_salary(raw):
    """Из пустой строки не берётся ни число, ни валюта."""
    assert parse_salary(raw) == (None, None, None)


def test_a_negotiable_salary_yields_no_range_despite_stray_numbers():
    """«По итогам собеседования» — не зарплата, даже если рядом есть числа."""
    assert parse_salary("по итогам собеседования, 30 дней отпуска") == (
        None,
        None,
        None,
    )


def test_a_rouble_range_is_kept_as_written():
    """Рублёвый диапазон остаётся тем же числом, каким записан."""
    assert parse_salary("150 000 — 300 000 ₽") == (150000, 300000, Currency.RUB)


def test_a_space_inside_a_number_does_not_break_it():
    """Пробел-разделитель разрядов не разрывает число надвое.

    Написание «$3 000» встречается в объявлениях наравне с «$3000», и разрыв
    на «3» и «000» превращал бы три тысячи долларов в диапазон от нуля до трёх.
    """
    assert parse_salary("$3 000") == (3000, 3000, Currency.USD)


def test_a_currency_amount_is_not_converted():
    """Валютное число не умножается ни на какой курс."""
    assert parse_salary("$3000-5000") == (3000, 5000, Currency.USD)


def test_a_single_number_gives_equal_bounds():
    """Одно число — диапазон из самого себя."""
    assert parse_salary("200000 ₽") == (200000, 200000, Currency.RUB)


@pytest.mark.parametrize("raw", ["300K", "300 тыс"])
def test_a_thousands_marker_is_expanded(raw):
    """Пометка тысяч раскрывается в число целиком."""
    assert parse_salary(raw) == (300000, 300000, None)


def test_a_cyrillic_thousands_marker_works_too():
    """Пометка тысяч кириллицей читается наравне с латинской."""
    assert parse_salary("от 250к до 400к ₽") == (250000, 400000, Currency.RUB)


def test_a_millions_marker_is_expanded_too():
    """«5 млн» — это пять миллионов, а не пять."""
    assert parse_salary("5 млн ₽") == (5000000, 5000000, Currency.RUB)


def test_bare_numbers_are_taken_at_face_value():
    """Голое число берётся как написано, без догадок о единицах."""
    assert parse_salary("1500-3000") == (1500, 3000, None)


def test_the_bounds_come_back_sorted():
    """Границы возвращаются по возрастанию независимо от порядка в строке."""
    assert parse_salary("300 000 — 150 000 ₽") == (150000, 300000, Currency.RUB)


@pytest.mark.parametrize(
    "raw, currency",
    [
        ("3000 долларов", Currency.USD),
        ("3000 USD", Currency.USD),
        ("2000 евро", Currency.EUR),
        ("2000 EUR", Currency.EUR),
        ("150000 руб.", Currency.RUB),
        ("150000 RUB", Currency.RUB),
    ],
)
def test_the_currency_is_recognised_by_word_as_well_as_by_sign(raw, currency):
    """Валюта опознаётся и знаком, и словом, и кодом."""
    assert parse_salary(raw)[2] is currency


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("оклад 100 000 ₽ + KPI", 100000),
        ("150000 ₽, Краснодар", 150000),
        ("150 000 ₽, пишите рекрутеру", 150000),
        ("$3000 per month", 3000),
        ("3000 USD/mo", 3000),
    ],
)
def test_a_letter_inside_a_word_is_not_a_thousands_marker(raw, expected):
    """Пометка тысяч и миллионов считается только своей у числа.

    «K» в «KPI», «к» в «Краснодаре», «m» в «month» — обычные буквы соседнего
    слова. Пока множитель искали по всей строке, любое из них умножало
    зарплату на тысячу или на миллион.
    """
    assert parse_salary(raw)[:2] == (expected, expected)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("$3,000", (3000, 3000)),
        ("150,000 - 300,000 RUB", (150000, 300000)),
    ],
)
def test_a_comma_between_thousands_does_not_break_the_number(raw, expected):
    """Запятая-разделитель разрядов не разрывает число.

    Английское «$3,000» распадалось на «3» и «000», и три тысячи долларов
    превращались в три.
    """
    assert parse_salary(raw)[:2] == expected


@pytest.mark.parametrize("raw", ["3.5к", "3,5к"])
def test_a_fraction_is_one_number_and_not_a_range(raw):
    """Дробное число остаётся одним числом, а не парой границ."""
    assert parse_salary(raw)[:2] == (3500, 3500)


def test_numbers_separated_by_a_line_break_stay_apart():
    """Перенос строки числа не склеивает."""
    assert parse_salary("150000\n200000")[:2] == (150000, 200000)


def test_a_percentage_is_not_a_salary():
    """Процент премии в границы зарплаты не попадает."""
    assert parse_salary("200 000 ₽ + KPI до 20%") == (200000, 200000, Currency.RUB)


def test_a_zero_bound_is_dropped():
    """Ноль зарплатой не бывает и нижней границей не становится."""
    assert parse_salary("от 0 до 300 000 ₽") == (300000, 300000, Currency.RUB)


@pytest.mark.parametrize(
    "raw", ["по трудовому договору, 200 000 ₽", "200 000 ₽, оформление по договору ГПХ"]
)
def test_a_contract_mention_does_not_hide_a_named_salary(raw):
    """Слово «договор» само по себе зарплату не отменяет.

    Отменяет её только «по договорённости»: там суммы нет вовсе, а «трудовой
    договор» и «договор ГПХ» стоят рядом с прямо названной суммой.
    """
    assert parse_salary(raw)[:2] == (200000, 200000)


@pytest.mark.parametrize("raw", ["по договорённости", "зарплата договорная"])
def test_a_salary_left_to_agreement_yields_nothing(raw):
    """«По договорённости» — не зарплата."""
    assert parse_salary(raw) == (None, None, None)


def test_a_currency_name_inside_a_word_is_not_the_currency():
    """«Европе» — не евро, и рублёвую вакансию в евро не превращает."""
    assert parse_salary("работа в Европе, 150000 руб")[2] is Currency.RUB


def test_two_currencies_at_once_leave_the_currency_unknown():
    """Когда названы две валюты, догадка запрещена.

    Диапазон «от 1000 $ до 2000 €» не имеет смысла ни в одной из них, и
    выбирать первую попавшуюся — значит прятать вакансию от отбора по второй.
    """
    assert parse_salary("от 1000 $ до 2000 €")[2] is None


def test_an_unnamed_currency_stays_unknown():
    """Не названная в строке валюта не додумывается.

    Догадка «раз без знака, значит рубли» отправила бы долларовую вакансию,
    записанную без знака, в рублёвую выдачу.
    """
    assert parse_salary("от 150000 до 200000")[2] is None
