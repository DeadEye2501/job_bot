"""Следствия отбора по строке и постраничности в списке HR.

Отбор идёт в питоне, а не в запросе: список HR невелик, и отбирать его после
выборки дешевле, чем городить условие на каждое искомое поле. Страница режется
после отбора: иначе предел выбирал бы из полного списка, а поиск отсеивал уже
выбранное.
"""

from backend.repository.hr_list import list_hr_with_counts
from tests.dbio import put
from tests.factories import hr_row


async def names(session, **kwargs) -> list[str]:
    """Имена HR в порядке выдачи."""
    return [row.hr.name for row in await list_hr_with_counts(session, **kwargs)]


async def test_search_looks_at_the_name_and_the_username(session, session_factory):
    """Поиск смотрит и в имя, и в ник."""
    await put(
        session_factory,
        hr_row(name="Анна", telegram_username="anna_hr"),
        hr_row(name="Борис", telegram_username="recruiter_b"),
        hr_row(name="Виктор", telegram_username="vik"),
    )

    assert await names(session, search="анна") == ["Анна"]
    assert await names(session, search="recruiter") == ["Борис"]


async def test_search_finds_capital_cyrillic(session, session_factory):
    """Поиск находит заглавную кириллицу любым написанием образца.

    Регистр складывает `casefold`, и складывает его у обеих сторон сразу —
    у образца и у значения.
    """
    await put(session_factory, hr_row(name="Мария"), hr_row(name="Ольга"))

    assert await names(session, search="Мария") == ["Мария"]
    assert await names(session, search="мария") == ["Мария"]
    assert await names(session, search="МАРИЯ") == ["Мария"]


async def test_a_blank_search_selects_everyone(session, session_factory):
    """Поиск из одних пробелов никого не отсекает."""
    await put(session_factory, hr_row(name="Анна"), hr_row(name="Борис"))

    assert await names(session, search="   ") == ["Анна", "Борис"]


async def test_the_page_is_cut_after_the_search_not_before(session, session_factory):
    """Страница режется после отбора, а не до него.

    Иначе предел выбирал бы строки из полного списка, а поиск отсеивал уже
    выбранное — и страница выходила бы короче предела или пустой.
    """
    await put(
        session_factory,
        hr_row(name="Анна", telegram_username="ivanova"),
        hr_row(name="Борис", telegram_username="petrov"),
        hr_row(name="Виктор", telegram_username="ivanov"),
        hr_row(name="Галина", telegram_username="ivanovskaya"),
    )

    assert await names(session, search="ivanov", limit=2) == ["Анна", "Виктор"]
    assert await names(session, search="ivanov", limit=2, offset=1) == [
        "Виктор",
        "Галина",
    ]
