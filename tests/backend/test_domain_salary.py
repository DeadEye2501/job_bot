"""Следствия, которые наблюдают тесты разбора зарплаты `backend/domain.py`.

Разбор намеренно приблизительный: его задача — питать фильтр диапазона в
списке вакансий, а не считать деньги. Поэтому проверяется не точность, а то,
что из строки достаётся диапазон в тысячах рублей и что мусор не превращается
в число.
"""

import pytest

from backend.domain import normalize_salary_to_rub_thousands as to_thousands


@pytest.mark.parametrize("raw", [None, "", "   ", "—"])
def test_nothing_is_extracted_from_a_blank_salary(raw):
    """Из пустой строки диапазон не берётся."""
    assert to_thousands(raw) == (None, None)


def test_a_negotiable_salary_yields_no_range_despite_stray_numbers():
    """«По итогам собеседования» — не зарплата, даже если рядом есть числа."""
    assert to_thousands("по итогам собеседования, 30 дней отпуска") == (None, None)


def test_a_plain_rouble_range_becomes_thousands():
    """Рублёвый диапазон переводится в тысячи."""
    assert to_thousands("150 000 — 300 000") == (150, 300)


def test_a_single_number_gives_equal_bounds():
    """Одно число — диапазон из самого себя."""
    assert to_thousands("200000") == (200, 200)


@pytest.mark.parametrize("raw", ["300K", "300 тыс"])
def test_a_thousands_marker_is_taken_at_face_value(raw):
    """При пометке тысяч число уже в тысячах и не делится."""
    assert to_thousands(raw) == (300, 300)


def test_a_cyrillic_thousands_marker_works_too():
    """Пометка тысяч кириллицей читается наравне с латинской."""
    assert to_thousands("от 250к до 400к") == (250, 400)


def test_a_millions_marker_multiplies_by_a_thousand():
    """«5 млн» — это пять тысяч тысяч."""
    assert to_thousands("5 млн") == (5000, 5000)


def test_small_bare_numbers_are_read_as_thousands():
    """Голое «1500-3000» правдоподобнее как тысячи, чем как рубли."""
    assert to_thousands("1500-3000") == (1500, 3000)


def test_the_bounds_come_back_sorted():
    """Границы возвращаются по возрастанию независимо от порядка в строке."""
    assert to_thousands("300 000 — 150 000") == (150, 300)


@pytest.mark.parametrize(
    "raw, expected",
    [("$3000-5000", (270000, 450000)), ("€2000", (200000, 200000))],
)
def test_a_currency_salary_is_multiplied_by_the_rate(raw, expected):
    """Валютная зарплата умножается на курс.

    ВНИМАНИЕ: закреплено текущее поведение, и оно подозревается ошибкой.
    Курс умножается на число, которое функция к этому моменту уже считает
    тысячами, поэтому «$3000» выходит как 270 000 тысяч рублей вместо 270.
    Тест держит поведение до того, как ошибку признают и починят отдельно;
    когда починят — он покраснеет, и это правильно. Находка записана в
    `docs/ROADMAP.md`.
    """
    assert to_thousands(raw) == expected


def test_the_rates_can_be_supplied_from_settings():
    """Курсы берутся переданные, а не только умолчания модуля.

    Числа несут тот же подозреваемый дефект, что и в
    `test_a_currency_salary_is_multiplied_by_the_rate`: курс умножается на
    уже-тысячи. Здесь проверяется сам факт использования переданного курса,
    а не корректность результата — при починке дефекта этот тест тоже
    покраснеет.
    """
    assert to_thousands("$3000", usd_rate=100) == (300000, 300000)
    assert to_thousands("€2000", eur_rate=110) == (220000, 220000)


def test_a_non_positive_rate_falls_back_to_the_default():
    """Нулевой или отрицательный курс из настроек заменяется умолчанием.

    Ожидаемое значение — то же 270 000 из подозреваемого дефекта
    (`test_a_currency_salary_is_multiplied_by_the_rate`), тест сравнивает с
    ним же, а не проверяет его корректность. При починке дефекта это
    сравнение тоже покраснеет.
    """
    assert to_thousands("$3000", usd_rate=0) == (270000, 270000)
