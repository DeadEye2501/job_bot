"""Названная сумма вакансии — по её вилке, анкете и кэшу курсов."""

from backend.models import SalaryPeriod
from backend.repository.vacancy_pay import pay_for_vacancy, vacancy_salary_lines
from tests.dbio import put
from tests.factories import profile_row, vacancy_row


async def test_a_foreign_ceiling_is_named_in_the_profile_currency(session, session_factory):
    """Курс рубля — 80, засеянный обвязкой."""
    await put(session_factory, profile_row(expected_salary=4000))
    vacancy = vacancy_row(salary="до 160 000 ₽", salary_max=160000,
                          salary_currency="₽", salary_period=SalaryPeriod.MONTH)
    await put(session_factory, vacancy)

    assert await vacancy_salary_lines(session, vacancy.id) == [
        "Зарплата для этой вакансии: 2000 $ в месяц, на руки"
    ]


async def test_no_vacancy_nothing_to_name(session):
    assert await pay_for_vacancy(session, 404) is None


async def test_no_profile_nothing_to_name(session, session_factory):
    vacancy = vacancy_row()
    await put(session_factory, vacancy)

    assert await vacancy_salary_lines(session, vacancy.id) == ["Зарплата для этой вакансии: не указана"]


async def test_an_hourly_sum_keeps_its_fraction(session, session_factory):
    await put(session_factory, profile_row(expected_salary=5, expected_salary_period=SalaryPeriod.HOUR))
    vacancy = vacancy_row(salary="$1500", salary_max=1500, salary_currency="$", salary_period=SalaryPeriod.MONTH)
    await put(session_factory, vacancy)

    assert await vacancy_salary_lines(session, vacancy.id) == [
        "Зарплата для этой вакансии: 8.9 $ в час, на руки"
    ]


async def test_a_ceiling_below_the_minimum_is_still_named_by_hand(session, session_factory):
    """Вакансию, заведённую вручную, отказ не отсеивает: называется её верх."""
    await put(session_factory, profile_row(minimum_salary=3500, expected_salary=4000))
    vacancy = vacancy_row(salary="до 3000 $", salary_max=3000, salary_currency="$",
                          salary_period=SalaryPeriod.MONTH)
    await put(session_factory, vacancy)

    assert await vacancy_salary_lines(session, vacancy.id) == [
        "Зарплата для этой вакансии: 3000 $ в месяц, на руки"
    ]
