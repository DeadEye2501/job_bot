"""Заглавная буква в названии компании.

Название компании человек читает в карточке, в строке списка и в отборе, и
набранное с маленькой буквы читается там опечаткой. Поднимается первая буква,
а не первый знак: у названия в кавычках или в скобках первый знак не буква, и
поднимать в нём нечего.

Исключение одно — написание, где вторая буква заглавная, а первая маленькая:
так пишут себя сами бренды, и поднятая первая буква не поправила бы имя, а
сломала.
"""

import pytest

from backend.domain.company_names import capitalized_company_name


@pytest.mark.parametrize(
    "name, expected",
    [
        pytest.param("ромашка", "Ромашка", id="кириллица"),
        pytest.param("acme", "Acme", id="латиница"),
        pytest.param("ромашка и сыновья", "Ромашка и сыновья", id="первое слово"),
        pytest.param("«ромашка»", "«Ромашка»", id="в кавычках"),
        pytest.param("(ромашка)", "(Ромашка)", id="в скобках"),
        pytest.param("1с-битрикс", "1С-битрикс", id="после цифры"),
    ],
)
def test_a_lowercase_name_gets_a_capital_letter(name, expected):
    """Название с маленькой буквы поднимается до заглавной."""
    assert capitalized_company_name(name) == expected


@pytest.mark.parametrize(
    "name",
    [
        pytest.param("eBay", id="eBay"),
        pytest.param("iFly", id="iFly"),
        pytest.param("«eBay»", id="в кавычках"),
    ],
)
def test_a_brand_with_a_capital_second_letter_is_left_alone(name):
    """Вторая буква заглавная при маленькой первой — написание бренда."""
    assert capitalized_company_name(name) == name


@pytest.mark.parametrize(
    "name",
    [
        pytest.param("Ромашка", id="уже с заглавной"),
        pytest.param("ООО «Акме»", id="заглавными"),
        pytest.param("", id="пусто"),
        pytest.param("   ", id="одни пробелы"),
        pytest.param("2ГИС", id="без своих букв в начале"),
    ],
)
def test_a_name_that_needs_nothing_is_returned_as_it_is(name):
    """Поднимать нечего — название отдаётся тем же."""
    assert capitalized_company_name(name) == name


def test_a_name_of_one_letter_is_raised():
    """Название из одной буквы поднимается: следующей буквы, которая запретила
    бы это, попросту нет."""
    assert capitalized_company_name("я") == "Я"


def test_nothing_stays_nothing():
    """Отсутствие названия остаётся отсутствием: поднимать нечего."""
    assert capitalized_company_name(None) is None


@pytest.mark.parametrize(
    "name",
    [
        pytest.param("x5 Retail", id="через цифру и пробел"),
        pytest.param("i-Free", id="через дефис"),
    ],
)
def test_a_capital_second_letter_holds_across_what_stands_between(name):
    """Исключение считает буквы, а не знаки.

    Между первой буквой и второй стоит то цифра с пробелом, то дефис, но
    вторая буква как была заглавной, так и осталась: «X5 Retail» и «I-Free»
    — уже не те написания, которыми компании зовут себя сами.
    """
    assert capitalized_company_name(name) == name


def test_a_name_that_is_an_address_keeps_its_scheme():
    """Имя, начинающееся адресом, не поднимается.

    Разбор оставляет в имени голую ссылку, когда ничего другого в поле не
    нашлось: пустое имя хуже грязного. Но «Https://kontur.ru» — не название с
    заглавной буквы, а испорченный адрес.
    """
    assert capitalized_company_name("https://kontur.ru") == "https://kontur.ru"

