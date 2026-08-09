"""Следствия порядка в списке чёрного списка на экране.

Порядок — по заведению. Раньше сортировали по включённости, и строка прыгала
между верхом и низом при каждом нажатии; устойчивость оказалась важнее
визуальной группировки.
"""

from backend.repository.blacklist import list_blacklist, set_blacklist_active
from tests.dbio import put
from tests.factories import blacklist_row


async def test_the_list_keeps_the_order_rows_were_added(session, session_factory):
    """Список идёт в порядке заведения, и переключение строку не двигает.

    Раньше сортировали по включённости, и строка прыгала между верхом и
    низом при каждом нажатии — устойчивый порядок оказался важнее.
    """
    first = blacklist_row("hr", "@первый", active=True)
    second = blacklist_row("channel", "@второй", active=False)
    third = blacklist_row("company", "Третья", active=True)
    await put(session_factory, first, second, third)

    await set_blacklist_active(session, first.id, False)
    await set_blacklist_active(session, second.id, True)

    assert [r.value for r in await list_blacklist(session)] == [
        "@первый",
        "@второй",
        "Третья",
    ]
