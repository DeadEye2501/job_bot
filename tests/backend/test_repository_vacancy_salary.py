"""Следствия разбора зарплаты и отбора по ней.

Зарплата хранится строкой как её написал автор объявления, поэтому отбор по
диапазону сначала вытаскивает из строки числа. Разбор понимает только доллары,
и вакансии, где валюта другая или не названа вовсе, из отбора выпадают — так
было и в том коде на JS, откуда разбор перенесён.
"""

import pytest

from backend.repository import _parse_usd_range
from tests.dbio import put
from tests.factories import vacancy_row


@pytest.mark.parametrize(
    "salary",
    [
        pytest.param(None, id="ничего не указано"),
        pytest.param("", id="пустая строка"),
        pytest.param("—", id="прочерк"),
        pytest.param("200000 ₽", id="рубли"),
        pytest.param("по договорённости", id="без чисел и без валюты"),
        pytest.param("$", id="доллар без чисел"),
        pytest.param("usd", id="валюта словом без чисел"),
    ],
)
def test_a_salary_without_parsable_dollars_yields_no_range(salary):
    """Строка без разбираемых долларов диапазона не даёт."""
    assert _parse_usd_range(salary) is None


@pytest.mark.parametrize(
    ("salary", "expected"),
    [
        pytest.param("$3000", (3000.0, 3000.0), id="одно число"),
        pytest.param("$3000-5000", (3000.0, 5000.0), id="диапазон"),
        pytest.param("5000-3000 usd", (3000.0, 5000.0), id="границы наоборот"),
        pytest.param("USD 3000", (3000.0, 3000.0), id="валюта словом в верхнем регистре"),
        pytest.param("$3k", (3000.0, 3000.0), id="тысячи латинской k"),
        pytest.param("$3к", (3000.0, 3000.0), id="тысячи кириллической к"),
        pytest.param("$3.5k", (3500.0, 3500.0), id="дробное через точку"),
        pytest.param("$3,5k", (3500.0, 3500.0), id="дробное через запятую"),
        pytest.param("$3 000", (0.0, 3.0), id="пробел внутри числа разрывает его"),
    ],
)
def test_a_dollar_salary_is_read_as_a_range(salary, expected):
    """Долларовая строка читается в диапазон от наименьшего к наибольшему.

    Последний случай — не описка. Пробел внутри числа выражение не склеивает,
    и «$3 000» распадается на «3» и «000», то есть на 3 и 0. Три тысячи
    долларов превращаются в диапазон от нуля до трёх, и отбор по любому
    осмысленному окну такую вакансию отбросит. Написание с пробелом-
    разделителем разрядов в объявлениях обычно. Тест закрепляет сегодняшнее
    поведение: при починке он покраснеет.
    """
    assert _parse_usd_range(salary) == expected


async def test_a_salary_range_keeps_the_overlapping_vacancies(titles, session_factory):
    """Отбор по зарплате оставляет вакансии, чей диапазон пересекается с заданным."""
    await put(
        session_factory,
        vacancy_row(title="ниже окна", salary="$1000-1500"),
        vacancy_row(title="краем задевает снизу", salary="$1500-2500"),
        vacancy_row(title="внутри окна", salary="$3000"),
        vacancy_row(title="краем задевает сверху", salary="$3500-6000"),
        vacancy_row(title="выше окна", salary="$6000-8000"),
    )

    got = await titles(salary_min=2000, salary_max=4000)

    assert sorted(got) == sorted(
        ["краем задевает снизу", "внутри окна", "краем задевает сверху"]
    )


async def test_an_unparsable_salary_drops_out_of_a_salary_filter(
    titles, session_factory
):
    """Вакансия с неразбираемой зарплатой из отбора по зарплате выпадает.

    Выпадает и та, где зарплата не указана вовсе, и та, где она в рублях:
    сравнить их с долларовым окном не с чем. Без отбора обе видны.
    """
    await put(
        session_factory,
        vacancy_row(title="в долларах", salary="$3000"),
        vacancy_row(title="в рублях", salary="300000 ₽"),
        vacancy_row(title="без зарплаты", salary=None),
    )

    assert await titles(salary_min=0) == ["в долларах"]
    assert len(await titles()) == 3


async def test_a_salary_filter_cancels_pagination(titles, session_factory):
    """При отборе по зарплате предел страницы не применяется.

    Отбор по зарплате идёт в питоне, уже после выборки, а `LIMIT` отрезал бы
    строки до того, как их проверили: страница вышла бы короче предела, а
    следующее смещение указывало бы мимо. Поэтому предел молча снимается, и
    возвращается весь отобранный список целиком.
    """
    await put(
        session_factory,
        *[vacancy_row(title=f"вакансия {n}", salary="$3000") for n in range(5)],
    )

    assert len(await titles(limit=2)) == 2
    assert len(await titles(limit=2, salary_min=1000)) == 5
