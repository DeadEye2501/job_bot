"""Следствия отбора по строке и постраничности в списке HR.

Отбор идёт в питоне, а не в запросе: список HR невелик, и отбирать его после
выборки дешевле, чем городить условие на каждое искомое поле. Страница режется
после отбора: иначе предел выбирал бы из полного списка, а поиск отсеивал уже
выбранное.
"""

from tests.dbio import put
from tests.factories import hr_row


async def test_search_looks_at_the_name_and_the_username(hr_names, session_factory):
    """Поиск смотрит и в имя, и в ник."""
    await put(
        session_factory,
        hr_row(name="Анна", telegram_username="anna_hr"),
        hr_row(name="Борис", telegram_username="recruiter_b"),
        hr_row(name="Виктор", telegram_username="vik"),
    )

    assert await hr_names(search="анна") == ["Анна"]
    assert await hr_names(search="recruiter") == ["Борис"]


async def test_search_finds_capital_cyrillic(hr_names, session_factory):
    """Поиск находит заглавную кириллицу любым написанием образца.

    Регистр складывает `casefold`, и складывает его у обеих сторон сразу —
    у образца и у значения.
    """
    await put(session_factory, hr_row(name="Мария"), hr_row(name="Ольга"))

    assert await hr_names(search="Мария") == ["Мария"]
    assert await hr_names(search="мария") == ["Мария"]
    assert await hr_names(search="МАРИЯ") == ["Мария"]


async def test_a_blank_search_selects_everyone(hr_names, session_factory):
    """Поиск из одних пробелов никого не отсекает."""
    await put(session_factory, hr_row(name="Анна"), hr_row(name="Борис"))

    assert await hr_names(search="   ") == ["Анна", "Борис"]


async def test_the_page_is_cut_after_the_search_not_before(hr_names, session_factory):
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

    assert await hr_names(search="ivanov", limit=2) == ["Анна", "Виктор"]
    assert await hr_names(search="ivanov", limit=2, offset=1) == [
        "Виктор",
        "Галина",
    ]
