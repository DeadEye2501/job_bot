"""Следствия переезда отметки чёрного списка вслед за именем компании.

Компанию в списке опознают одним написанием — её нынешним именем. Имя
меняется дважды: его правит карточка, и оно перестаёт быть именем при
слиянии. Останься строка списка на прежнем написании — она продолжила бы
отбрасывать посты, а из карточки пропала бы, и снять её было бы нечем.
"""

from sqlalchemy import select

from backend.models import Blacklist
from backend.repository.companies_card import (
    get_company_detail,
    merge_company,
    update_company_fields,
)
from tests.dbio import put
from tests.factories import blacklist_row, company_row


async def test_the_mark_follows_the_renamed_company(session, session_factory):
    """Переименованная компания остаётся отмеченной, и отметка зовётся новым
    именем.

    Прежнее написание не должно пережить правку: оно уже ничьё, а отсев по
    нему идёт дальше.
    """
    company = company_row(name="Ромашка")
    await put(session_factory, company)
    await put(session_factory, blacklist_row("company", "Ромашка"))

    await update_company_fields(session, company.id, name="Ромашка Групп")

    assert (
        await get_company_detail(session, company.id)
    ).blacklist_value == "Ромашка Групп"
    rows = (await session.scalars(select(Blacklist))).all()
    assert [(row.value, row.active) for row in rows] == [("Ромашка Групп", True)]


async def test_a_mark_of_another_kind_stays_where_it_was(session, session_factory):
    """Одноимённая отметка другого рода за компанией не едет.

    Человека и компанию зовут одинаково чаще, чем кажется, а род — это и есть
    ответ на вопрос, кого отсеивают.
    """
    company = company_row(name="Ромашка")
    await put(session_factory, company)
    await put(
        session_factory,
        blacklist_row("company", "Ромашка"),
        blacklist_row("hr", "Ромашка"),
    )

    await update_company_fields(session, company.id, name="Ромашка Групп")

    rows = (await session.scalars(select(Blacklist))).all()
    assert sorted((row.kind, row.value) for row in rows) == [
        ("company", "Ромашка Групп"),
        ("hr", "Ромашка"),
    ]


async def test_the_mark_of_the_absorbed_moves_to_the_survivor(
    session, session_factory
):
    """Отметка поглощённой компании достаётся оставшейся.

    Слияние необратимо: имя поглощённой становится написанием, а отсев,
    заведённый на неё, должен остаться видимым — теперь в карточке
    оставшейся.
    """
    absorbed = company_row(name="Ромашка")
    survivor = company_row(name="Ромашка Групп")
    await put(session_factory, absorbed, survivor)
    await put(session_factory, blacklist_row("company", "Ромашка"))

    await merge_company(session, absorbed_id=absorbed.id, survivor_id=survivor.id)

    assert (
        await get_company_detail(session, survivor.id)
    ).blacklist_value == "Ромашка Групп"


async def test_two_marked_companies_leave_one_active_mark(session, session_factory):
    """Слияние двух отмеченных компаний оставляет одну действующую отметку.

    Вторая строка с тем же написанием не заводится: заведение из карточки её
    тоже не допускает, а погашенная остаётся видимой на экране списка.
    """
    absorbed = company_row(name="Ромашка")
    survivor = company_row(name="Берёзка")
    await put(session_factory, absorbed, survivor)
    await put(
        session_factory,
        blacklist_row("company", "Ромашка"),
        blacklist_row("company", "Берёзка"),
    )

    await merge_company(session, absorbed_id=absorbed.id, survivor_id=survivor.id)

    rows = (await session.scalars(select(Blacklist))).all()
    assert sorted((row.value, row.active) for row in rows) == [
        ("Берёзка", True),
        ("Ромашка", False),
    ]


async def test_a_switched_off_mark_of_the_survivor_lights_up(
    session, session_factory
):
    """Погашенная отметка оставшейся оживает, если отмечена поглощённая.

    Отсев заводили на оба имени, у оставшейся его потом сняли — а теперь в неё
    вливают компанию, которая в отсеве. Оставь строку погашенной, и слияние
    молча сняло бы отметку, которую никто не снимал: с поглощённой она
    исчезает вместе с именем.
    """
    absorbed = company_row(name="Ромашка")
    survivor = company_row(name="Берёзка")
    await put(session_factory, absorbed, survivor)
    await put(
        session_factory,
        blacklist_row("company", "Ромашка"),
        blacklist_row("company", "Берёзка", active=False),
    )

    await merge_company(session, absorbed_id=absorbed.id, survivor_id=survivor.id)

    assert (
        await get_company_detail(session, survivor.id)
    ).blacklist_value == "Берёзка"
