"""Следствия сборки карточки компании для боковой панели контактов.

Карточка складывается вокруг одной строки: сколько у компании вакансий,
сколько разных HR о них написали и стоит ли компания в чёрном списке. У
компании нет второго опознавательного признака вроде ника, поэтому в списке
её записывают именем — единственным написанием.
"""

from backend.repository.blacklist_marks import preferred_blacklist_value
from backend.repository.companies_card import company_blacklist_candidates, get_company_detail
from backend.repository.hr_list import list_hrs_for_company
from tests.dbio import put
from tests.factories import blacklist_row, company_row, hr_row, vacancy_row


async def test_a_missing_company_has_no_card(session, session_factory):
    """У несуществующей компании карточки нет, и это не ошибка."""
    await put(session_factory, company_row())

    assert await get_company_detail(session, 10_000) is None


async def test_a_fresh_company_has_zeroes(session, session_factory):
    """У свежей компании счётчики нулевые, отметки списка нет."""
    company = company_row()
    await put(session_factory, company)

    card = await get_company_detail(session, company.id)

    assert card.vacancy_count == 0
    assert card.hr_count == 0
    assert card.blacklist_value is None


async def test_the_counts_are_about_this_company_only(session, session_factory):
    """Счётчики считают вакансии этой компании, а не все подряд."""
    mine = company_row(name="Контур")
    other = company_row(name="Ромашка")
    await put(session_factory, mine, other)
    await put(
        session_factory,
        vacancy_row(company_id=mine.id),
        vacancy_row(company_id=mine.id),
        vacancy_row(company_id=other.id),
        vacancy_row(company_id=None),
    )

    card = await get_company_detail(session, mine.id)

    assert card.vacancy_count == 2


async def test_one_hr_with_many_vacancies_counts_once(session, session_factory):
    """Один HR с несколькими вакансиями считается за одного.

    Счётчик в шапке отвечает на вопрос «сколько людей о ней писали», а не
    «сколько вакансий пришло».
    """
    company = company_row()
    await put(session_factory, company)
    busy = hr_row(name="Анна")
    single = hr_row(name="Борис")
    await put(session_factory, busy, single)
    await put(
        session_factory,
        vacancy_row(company_id=company.id, hr_id=busy.id),
        vacancy_row(company_id=company.id, hr_id=busy.id),
        vacancy_row(company_id=company.id, hr_id=single.id),
        vacancy_row(company_id=company.id, hr_id=None),
    )

    card = await get_company_detail(session, company.id)

    assert card.vacancy_count == 4
    assert card.hr_count == 2


async def test_an_unparsed_vacancy_is_counted_by_neither_counter(
    session, session_factory
):
    """Неразобранная вакансия не идёт ни в один счётчик карточки.

    Оба отвечают на один вопрос — что мы про эту компанию знаем, — а у
    неразобранной строки и сама принадлежность компании ещё не установлена:
    её проставит разбор, который не дошёл.
    """
    company = company_row()
    await put(session_factory, company)
    hr = hr_row(name="Анна")
    await put(session_factory, hr)
    await put(
        session_factory,
        vacancy_row(company_id=company.id, hr_id=hr.id, is_parsed=False),
    )

    card = await get_company_detail(session, company.id)

    assert card.vacancy_count == 0
    assert card.hr_count == 0


def test_a_company_is_listed_by_its_name_alone():
    """В чёрном списке компанию записывают именем — другого признака у неё нет."""
    assert company_blacklist_candidates(company_row(name="Контур")) == ["Контур"]
    assert preferred_blacklist_value(
        company_blacklist_candidates(company_row(name="Контур"))
    ) == "Контур"


async def test_the_card_shows_an_active_mark_of_its_own_kind(
    session, session_factory
):
    """Отметка показывается, только если она включена и заведена для компании."""
    listed = company_row(name="Контур")
    switched_off = company_row(name="Ромашка")
    other_kind = company_row(name="Берёзка")
    await put(session_factory, listed, switched_off, other_kind)
    await put(
        session_factory,
        blacklist_row("company", "Контур"),
        blacklist_row("company", "Ромашка", active=False),
        blacklist_row("hr", "Берёзка"),
    )

    assert (await get_company_detail(session, listed.id)).blacklist_value == "Контур"
    assert (await get_company_detail(session, switched_off.id)).blacklist_value is None
    assert (await get_company_detail(session, other_kind.id)).blacklist_value is None


async def test_the_hr_list_leads_with_the_one_who_brought_more(
    session, session_factory
):
    """Список HR компании ведёт тот, кто принёс больше вакансий.

    Порядок вставки обратен ожидаемому: совпади они — и выдача без всякой
    сортировки прошла бы проверку.
    """
    company = company_row()
    await put(session_factory, company)
    few = hr_row(name="Борис")
    many = hr_row(name="Анна")
    await put(session_factory, few, many)
    await put(
        session_factory,
        vacancy_row(company_id=company.id, hr_id=few.id),
        vacancy_row(company_id=company.id, hr_id=many.id),
        vacancy_row(company_id=company.id, hr_id=many.id),
    )

    got = await list_hrs_for_company(session, company.id)

    assert [(hr.name, n) for hr, n in got] == [("Анна", 2), ("Борис", 1)]


async def test_an_equal_share_is_broken_by_name(session, session_factory):
    """При равном вкладе порядок решает имя.

    Проверено мутацией: на двух строках снятие разрешителя проходило молча —
    база и без него возвращала нужную пару. Здесь их три, и ни порядок
    заведения, ни обратный ему с ожидаемым не совпадают.
    """
    company = company_row()
    await put(session_factory, company)
    third = hr_row(name="Яна")
    first = hr_row(name="Анна")
    second = hr_row(name="Борис")
    await put(session_factory, third, first, second)
    await put(
        session_factory,
        vacancy_row(company_id=company.id, hr_id=third.id),
        vacancy_row(company_id=company.id, hr_id=first.id),
        vacancy_row(company_id=company.id, hr_id=second.id),
    )

    got = await list_hrs_for_company(session, company.id)

    assert [hr.name for hr, _ in got] == ["Анна", "Борис", "Яна"]


async def test_hrs_of_another_company_stay_out(session, session_factory):
    """HR другой компании в список не попадают."""
    mine = company_row(name="Контур")
    other = company_row(name="Ромашка")
    await put(session_factory, mine, other)
    ours = hr_row(name="Анна")
    theirs = hr_row(name="Борис")
    await put(session_factory, ours, theirs)
    await put(
        session_factory,
        vacancy_row(company_id=mine.id, hr_id=ours.id),
        vacancy_row(company_id=other.id, hr_id=theirs.id),
    )

    got = await list_hrs_for_company(session, mine.id)

    assert [hr.name for hr, _ in got] == ["Анна"]
