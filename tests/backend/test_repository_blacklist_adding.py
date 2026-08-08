"""Следствия заведения строки чёрного списка.

Заведение сводит повторы само: одна и та же пара «род, значение» не может
лежать двумя строками, а погашенная запись при повторном добавлении оживает,
а не заводится заново — иначе история решений росла бы копиями.
"""

import pytest
from sqlalchemy import select

from backend.models import Blacklist
from backend.repository import BlacklistUpdateError, create_blacklist
from tests.dbio import put
from tests.factories import blacklist_row


async def test_a_new_row_is_created_active(session):
    """Новая строка заводится включённой, и об этом сообщается."""
    row, created = await create_blacklist(
        session, kind="hr", value="  @maria  ", reason="  грубит  "
    )

    assert created is True
    assert row.kind == "hr"
    assert row.value == "@maria"
    assert row.reason == "грубит"
    assert row.active is True


async def test_an_empty_value_or_kind_is_refused(session):
    """Пустое значение и пустой род отвергаются.

    Пустое значение бесполезно: оно ни с чем не совпадёт, а на экране
    выглядит как незаполненная строка-заготовка.
    """
    with pytest.raises(BlacklistUpdateError, match="Значение"):
        await create_blacklist(session, kind="hr", value="   ")
    with pytest.raises(BlacklistUpdateError, match="Тип"):
        await create_blacklist(session, kind="  ", value="@maria")


async def test_an_empty_reason_is_stored_as_absence(session):
    """Пустая причина записывается как отсутствие, а не как пустая строка."""
    row, _ = await create_blacklist(session, kind="hr", value="@maria", reason="   ")

    assert row.reason is None


async def test_adding_the_same_pair_twice_returns_the_first_row(
    session, session_factory
):
    """Повторное добавление той же пары отдаёт прежнюю строку, а не заводит вторую."""
    existing = blacklist_row("hr", "@maria", reason="грубит")
    await put(session_factory, existing)

    row, created = await create_blacklist(session, kind="hr", value="@maria")

    assert created is False
    assert row.id == existing.id
    assert len((await session.scalars(select(Blacklist))).all()) == 1


async def test_the_same_value_of_another_kind_is_a_separate_row(
    session, session_factory
):
    """То же значение другого рода — отдельная строка.

    В одной таблице лежат записи и про людей, и про каналы: «@maria» может
    оказаться и ником человека, и ником канала.
    """
    await put(session_factory, blacklist_row("hr", "@maria"))

    row, created = await create_blacklist(session, kind="channel", value="@maria")

    assert created is True
    assert row.kind == "channel"


async def test_adding_a_switched_off_pair_switches_it_back_on(
    session, session_factory
):
    """Повторное добавление погашенной пары включает её обратно."""
    existing = blacklist_row("hr", "@maria", active=False)
    await put(session_factory, existing)

    row, created = await create_blacklist(session, kind="hr", value="@maria")

    assert created is False
    assert row.active is True


async def test_a_reason_fills_an_empty_one_but_never_replaces_it(
    session, session_factory
):
    """Причина при повторном добавлении заполняет пустую, но не затирает прежнюю."""
    empty = blacklist_row("hr", "@maria", reason=None)
    filled = blacklist_row("hr", "@olga", reason="первая причина")
    await put(session_factory, empty, filled)

    got_new, _ = await create_blacklist(
        session, kind="hr", value="@maria", reason="новая причина"
    )
    kept_old, _ = await create_blacklist(
        session, kind="hr", value="@olga", reason="новая причина"
    )

    assert got_new.reason == "новая причина"
    assert kept_old.reason == "первая причина"
