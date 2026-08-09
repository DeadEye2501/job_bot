"""Следствия отбора вакансий по зарплате.

Отбор идёт по числам, записанным при разборе объявления, — по колонкам
`salary_min`/`salary_max`, а не по строке, которую видит человек. Строку
разбирает домен, и здесь она не участвует вовсе: сюда приходит уже число.

Валюта в отборе не участвует: «больше 3000» находит и три тысячи долларов, и
три тысячи рублей. Отделять одно от другого — дело отдельного поля фильтра.
"""

from tests.dbio import put
from tests.factories import vacancy_row


async def test_a_salary_range_keeps_the_overlapping_vacancies(titles, session_factory):
    """Отбор по зарплате оставляет вакансии, чей диапазон пересекается с заданным."""
    await put(
        session_factory,
        vacancy_row(title="ниже окна", salary_min=1000, salary_max=1500),
        vacancy_row(title="краем задевает снизу", salary_min=1500, salary_max=2500),
        vacancy_row(title="внутри окна", salary_min=3000, salary_max=3000),
        vacancy_row(title="краем задевает сверху", salary_min=3500, salary_max=6000),
        vacancy_row(title="выше окна", salary_min=6000, salary_max=8000),
    )

    got = await titles(salary_min=2000, salary_max=4000)

    assert sorted(got) == sorted(
        ["краем задевает снизу", "внутри окна", "краем задевает сверху"]
    )


async def test_the_written_string_takes_no_part_in_the_filter(titles, session_factory):
    """Отбор смотрит в числа, а не в строку, которую видит человек.

    До переписывания он разбирал строку заново и в абсолютных долларах: всё,
    что не в долларах, выбрасывалось из выдачи молча — рублёвая вакансия не
    находилась ни одним окном.
    """
    await put(
        session_factory,
        vacancy_row(title="в долларах", salary="$3000", salary_min=3000, salary_max=3000),
        vacancy_row(title="в рублях", salary="3000 ₽", salary_min=3000, salary_max=3000),
    )

    assert sorted(await titles(salary_min=2000)) == ["в долларах", "в рублях"]


async def test_a_vacancy_without_a_number_drops_out_of_a_salary_filter(
    titles, session_factory
):
    """Вакансия без числа в зарплате из отбора по зарплате выпадает.

    Сравнить её с окном не с чем. Без отбора она видна.
    """
    await put(
        session_factory,
        vacancy_row(title="с числом", salary_min=3000, salary_max=3000),
        vacancy_row(title="без зарплаты", salary="по договорённости"),
    )

    assert await titles(salary_min=0) == ["с числом"]
    assert await titles(salary_max=100000) == ["с числом"]
    assert len(await titles()) == 2


async def test_the_salary_window_includes_both_of_its_own_ends(titles, session_factory):
    """Границы окна входят в него сами.

    Без этого случая замена нестрогого сравнения на строгое проходит молча: у
    остальных вакансий числа окна в точности не задевают, и «не меньше» от
    «больше» там неотличимо.
    """
    await put(
        session_factory,
        vacancy_row(title="ровно нижняя", salary_min=3000, salary_max=3000),
        vacancy_row(title="ровно верхняя", salary_min=5000, salary_max=5000),
        vacancy_row(title="на волос ниже", salary_min=2999, salary_max=2999),
        vacancy_row(title="на волос выше", salary_min=5001, salary_max=5001),
    )

    got = await titles(salary_min=3000, salary_max=5000)

    assert sorted(got) == sorted(["ровно нижняя", "ровно верхняя"])


async def test_only_the_lower_bound_leaves_the_upper_open(titles, session_factory):
    """Заданная одна граница вторую не додумывает."""
    await put(
        session_factory,
        vacancy_row(title="мало", salary_min=1000, salary_max=1000),
        vacancy_row(title="много", salary_min=9000, salary_max=9000),
    )

    assert await titles(salary_min=5000) == ["много"]
    assert await titles(salary_max=5000) == ["мало"]


async def test_a_salary_filter_no_longer_cancels_pagination(titles, session_factory):
    """При отборе по зарплате предел страницы работает как у любого другого.

    Отбор переехал в запрос, поэтому `LIMIT` больше не может отрезать строки
    до того, как их проверили.
    """
    await put(
        session_factory,
        *[
            vacancy_row(title=f"вакансия {n}", salary_min=3000, salary_max=3000)
            for n in range(5)
        ],
    )

    assert len(await titles(limit=2)) == 2
    assert len(await titles(limit=2, salary_min=1000)) == 2
