"""Следствия чтения самого числа в строке зарплаты.

Разбор ничего не пересчитывает: число остаётся тем, что записано в
объявлении, — раскрывается только пометка тысяч и миллионов, без которой
«300к» не сравнить с «300000». Здесь проверяется, что число не разваливается
на разрядах и не собирается из чужих цифр; что при этом считать зарплатой —
предмет соседнего файла.
"""

import pytest

from backend.domain.salary import parse_salary
from backend.models import Currency


def test_a_space_inside_a_number_does_not_break_it():
    """Пробел-разделитель разрядов не разрывает число надвое.

    Написание «$3 000» встречается в объявлениях наравне с «$3000», и разрыв
    на «3» и «000» превращал бы три тысячи долларов в диапазон от нуля до трёх.
    """
    assert parse_salary("$3 000") == (3000, 3000, Currency.USD)


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
    "raw, expected",
    [
        ("оклад 100 000 ₽ + KPI", 100000),
        ("150000 ₽, Краснодар", 150000),
        ("150 000 ₽, пишите рекрутеру", 150000),
        ("$3000 per month", 3000),
        ("3000 USD/mo", 3000),
        ("$3000 monthly", 3000),
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


def test_a_percentage_is_not_a_salary():
    """Процент премии в границы зарплаты не попадает."""
    assert parse_salary("200 000 ₽ + KPI до 20%") == (200000, 200000, Currency.RUB)


def test_a_zero_bound_is_dropped():
    """Ноль зарплатой не бывает и нижней границей не становится.

    Уцелевшая сторона вилки остаётся собой: «от 0 до 300 000» значит «не
    больше трёхсот тысяч», а не «ровно триста». Поставь ноль нижней границей
    или повтори триста тысяч обеими — вакансия попадёт в отбор «от 300 000»,
    хотя платить столько никто не обещал.
    """
    assert parse_salary("от 0 до 300 000 ₽") == (None, 300000, Currency.RUB)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("$1,000.50", 1000),
        ("€3.000,50", 3000),
        ("150.000,00 руб", 150000),
    ],
)
def test_a_number_with_both_separators_is_read_and_does_not_blow_up(raw, expected):
    """Разряды и дробная часть в одном числе разбираются, а не роняют разбор.

    Написание «$1,000.50» — обычное английское. Пока десятичный знак и
    разделитель разрядов не были разведены, такое число не просто читалось
    неверно — оно бросало, а вылетевший разбор оставлял вакансию
    неразобранной навсегда: конвейер брал её заново при каждом запуске.
    """
    assert parse_salary(raw)[:2] == (expected, expected)


@pytest.mark.parametrize("space", [" ", " ", " "])
def test_a_typographic_space_inside_a_number_does_not_break_it(space):
    """Неразрывный и узкий пробелы внутри числа читаются наравне с обычным.

    Именно их ставит типографика, и именно они приезжают из объявлений
    Telegram. Обычный пробел в такой строке — скорее исключение.
    """
    assert parse_salary(f"200{space}000 ₽") == (200000, 200000, Currency.RUB)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("300 тысяч ₽", 300000),
        ("300 тыс. ₽", 300000),
        ("1 миллион рублей", 1000000),
    ],
)
def test_a_marker_written_out_in_full_is_a_marker_too(raw, expected):
    """Пометка, написанная словом целиком, читается наравне с сокращением."""
    assert parse_salary(raw)[:2] == (expected, expected)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("150-200 тыс руб", (150000, 200000)),
        ("от 100 до 150 к", (100000, 150000)),
        ("зарплата 100 — 150 тыс", (100000, 150000)),
    ],
)
def test_a_marker_at_the_end_of_a_range_covers_the_whole_range(raw, expected):
    """Пометка в конце вилки относится ко всей вилке, а не к одному числу.

    «150-200 тыс» — это сто пятьдесят и двести тысяч. Пока пометка
    доставалась только своему числу, в одну строку ложились сто пятьдесят
    рублей и двести тысяч рублей разом.
    """
    assert parse_salary(raw)[:2] == expected


def test_a_number_too_big_for_the_column_is_dropped():
    """Число, не влезающее в колонку, зарплатой не считается.

    Модель пишет строку зарплаты дословно, и в неё попадает что угодно —
    например, слипшийся ряд цифр. Записать такое значит уронить разбор
    вакансии на коммите и оставить её неразобранной навсегда.
    """
    assert parse_salary("1234567890123456789012345 ₽") == (None, None, None)
