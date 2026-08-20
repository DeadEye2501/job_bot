"""Следствия сборки списка компаний со счётчиками.

Порядок один: вперёд те, у кого вакансий больше, при равенстве — по имени.
Отбор по строке идёт в питоне и смотрит в три места сразу — имя, написания и
сайт, — потому что искать компанию пользователь может по любому из них.
"""

from backend.repository.companies_list import list_companies_with_counts
from tests.dbio import put
from tests.factories import company_marks, company_row, marked_companies, vacancy_row


async def names(session, **kwargs) -> list[str]:
    """Названия компаний в порядке выдачи."""
    rows, _ = await list_companies_with_counts(session, **kwargs)
    return [row.company.name for row in rows]


async def test_the_list_leads_with_the_most_prolific_company(
    session, session_factory
):
    """Вперёд идёт компания с наибольшим числом вакансий.

    Порядок вставки обратен ожидаемому: совпади они — и выдача без
    сортировки прошла бы проверку.
    """
    none_at_all = company_row(name="Берёзка")
    few = company_row(name="Ромашка")
    many = company_row(name="Контур")
    await put(session_factory, none_at_all, few, many)
    await put(
        session_factory,
        vacancy_row(company_id=many.id),
        vacancy_row(company_id=many.id),
        vacancy_row(company_id=few.id),
    )

    assert await names(session) == ["Контур", "Ромашка", "Берёзка"]


async def test_an_equal_count_is_broken_by_name(session, session_factory):
    """При равном числе вакансий порядок решает имя."""
    await put(
        session_factory,
        company_row(name="Ясень"),
        company_row(name="Акация"),
        company_row(name="Берёза"),
    )

    assert await names(session) == ["Акация", "Берёза", "Ясень"]


async def test_search_looks_at_the_name_the_aliases_and_the_website(
    session, session_factory
):
    """Поиск смотрит в имя, в написания и в сайт."""
    await put(
        session_factory,
        company_row(name="Контур", aliases=[], website=None),
        company_row(name="Ромашка", aliases=["Romashka Tech"], website=None),
        company_row(name="Берёзка", aliases=[], website="https://bereza.dev"),
        company_row(name="Мимо", aliases=[], website=None),
    )

    assert await names(session, search="контур") == ["Контур"]
    assert await names(session, search="romashka") == ["Ромашка"]
    assert await names(session, search="bereza.dev") == ["Берёзка"]


async def test_search_finds_capital_cyrillic(session, session_factory):
    """Поиск находит заглавную кириллицу в любом написании образца.

    Регистр складывает `casefold`, и складывает его у обеих сторон сразу —
    у образца и у значения.
    """
    await put(session_factory, company_row(name="Ромашка"), company_row(name="Контур"))

    assert await names(session, search="Ромашка") == ["Ромашка"]
    assert await names(session, search="РОМАШКА") == ["Ромашка"]


async def test_a_non_string_alias_does_not_break_the_search(session, session_factory):
    """Не-строка среди написаний поиск не роняет.

    Список написаний лежит в колонке JSON, и туда могло попасть что угодно —
    из старых данных или чужой правкой базы.
    """
    await put(session_factory, company_row(name="Ромашка", aliases=[42, None, "Romashka"]))

    assert await names(session, search="romashka") == ["Ромашка"]
    assert await names(session, search="контур") == []


async def test_a_spellings_column_that_is_not_a_list_does_not_break_the_pane(
    session, session_factory
):
    """Не-список на месте написаний не роняет перечень компаний.

    Роняет он его не при поиске, а всегда: перебор написаний идёт через
    разворачивание, и не-список не развернулся бы даже тогда, когда искать
    не просили.
    """
    await put(session_factory, company_row(name="Ромашка", aliases=42))

    assert await names(session) == ["Ромашка"]
    assert await names(session, search="ромашка") == ["Ромашка"]


async def test_the_page_is_cut_after_the_search(session, session_factory):
    """Страница режется после отбора, а не до него."""
    await put(
        session_factory,
        company_row(name="Акация", website="https://tech.example"),
        company_row(name="Берёза", website=None),
        company_row(name="Вишня", website="https://tech.example"),
        company_row(name="Груша", website="https://tech.example"),
    )

    assert await names(session, search="tech.example", limit=2) == ["Акация", "Вишня"]
    assert await names(session, search="tech.example", limit=2, offset=1) == [
        "Вишня",
        "Груша",
    ]


async def test_the_row_carries_its_count_and_blacklist_mark(session, session_factory):
    """В строке списка едут счётчик вакансий и отметка чёрного списка."""
    listed, switched_off, other_kind = marked_companies()
    await put(session_factory, listed, switched_off, other_kind)
    await put(session_factory, vacancy_row(company_id=listed.id), *company_marks())

    found, _ = await list_companies_with_counts(session)
    rows = {r.company.name: r for r in found}

    assert rows["Контур"].vacancy_count == 1
    assert rows["Контур"].is_blacklisted is True
    assert rows["Ромашка"].is_blacklisted is False
    assert rows["Берёзка"].is_blacklisted is False


async def test_an_unparsed_vacancy_is_not_counted(session, session_factory):
    """Недоразобранная вакансия в счётчик компании не идёт.

    Мини-список карточки показывает только разобранные, и посчитанная она
    развела бы число в строке со списком под ним.
    """
    company = company_row(name="Контур")
    await put(session_factory, company)
    await put(
        session_factory,
        vacancy_row(company_id=company.id),
        vacancy_row(company_id=company.id, is_parsed=False, title=None),
    )

    found, _ = await list_companies_with_counts(session)
    rows = {r.company.name: r for r in found}

    assert rows["Контур"].vacancy_count == 1
