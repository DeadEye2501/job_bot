"""Агрегатор в чёрном списке: запись по хосту, гашение, запрет включения и обхода.

Правило то же, что у канала: источник в отсеве не работает. Отметка агрегатора
— его хост в нормальной форме; у «Поиска по сети» хоста нет, и отметить его
нечем.
"""

import pytest

from backend.models import Aggregator
from backend.repository.aggregators import (
    get_aggregator_detail, list_aggregators_with_counts, round_sources, set_aggregator_active,
)
from backend.repository.blacklist import (
    BlacklistUpdateError, create_blacklist, set_blacklist_active, update_blacklist,
)
from backend.repository.blacklist_candidates import list_blacklist_candidates
from tests.dbio import all_rows, put
from tests.factories import blacklist_row
from tests.factories_aggregators import aggregator_row, web_search_row


async def test_a_typed_address_is_stored_as_the_host(session):
    """Набранное как угодно сводится к хосту: по нему отметку и ищут."""
    async with session.begin():
        row, _ = await create_blacklist(session, kind="aggregator", value="https://www.Site.test/jobs")
    assert row.value == "site.test"


async def test_an_address_without_a_host_is_refused(session):
    with pytest.raises(BlacklistUpdateError, match="сайт"):
        await create_blacklist(session, kind="aggregator", value="https://")


async def test_an_address_edited_in_place_is_stored_as_the_host_too(session, session_factory):
    """Правка на месте — не дорога в обход: набранный адрес целиком не совпал
    бы с агрегатором, и тот тихо вышел бы из отсева при действующей записи."""
    barred = aggregator_row(host="site.test", is_active=True, is_logged_in=True)
    entry = blacklist_row(kind="aggregator", value="old.test")
    await put(session_factory, barred, entry)

    async with session.begin():
        await update_blacklist(session, entry.id, value="https://www.Site.test/")

    (row,) = [one for one in await all_rows(session_factory, Aggregator) if one.host == "site.test"]
    assert row.is_active is False
    async with session_factory() as fresh:
        assert (await fresh.get(type(entry), entry.id)).value == "site.test"


async def test_a_mark_on_a_site_covers_its_subdomain_aggregator(session, session_factory):
    """Поддомен сайта — тот же сайт, как и в отсеве ссылок: агрегатор на
    поддомене отмеченного сайта гаснет, не включается, не обходится и помечен."""
    sub = aggregator_row(host="spb.site.test", is_active=True, is_logged_in=True)
    await put(session_factory, sub)

    async with session.begin():
        await create_blacklist(session, kind="aggregator", value="site.test")

    (row,) = await all_rows(session_factory, Aggregator)
    assert row.is_active is False
    async with session_factory() as fresh:
        async with fresh.begin():
            assert await set_aggregator_active(fresh, sub.id, True) == "blacklisted"
        assert await round_sources(fresh) == []
        (listed,) = await list_aggregators_with_counts(fresh)
        assert listed[2] is True


async def test_an_entry_switches_the_aggregator_off(session, session_factory):
    barred = aggregator_row(host="site.test", is_active=True, is_logged_in=True)
    clean = aggregator_row(host="other.test", is_active=True, is_logged_in=True)
    await put(session_factory, barred, clean)

    async with session.begin():
        await create_blacklist(session, kind="aggregator", value="site.test")

    rows = await all_rows(session_factory, Aggregator)
    assert {a.host: a.is_active for a in rows} == {"site.test": False, "other.test": True}


async def test_switching_an_entry_back_on_switches_the_aggregator_off(session, session_factory):
    site = aggregator_row(host="site.test", is_active=True, is_logged_in=True)
    entry = blacklist_row("aggregator", "site.test", active=False)
    await put(session_factory, site, entry)

    async with session.begin():
        await set_blacklist_active(session, entry.id, True)

    assert [a.is_active for a in await all_rows(session_factory, Aggregator)] == [False]


async def test_a_blacklisted_aggregator_cannot_be_switched_on(session, session_factory):
    site = aggregator_row(host="site.test", is_logged_in=True)
    await put(session_factory, site, blacklist_row("aggregator", "site.test"))

    async with session.begin():
        assert await set_aggregator_active(session, site.id, True) == "blacklisted"
    assert [a.is_active for a in await all_rows(session_factory, Aggregator)] == [False]


async def test_the_round_skips_a_blacklisted_aggregator_even_when_switched_on(
    session, session_factory
):
    """Строку могли включить мимо окна; обход всё равно её не берёт, а «Поиск по сети» — берёт."""
    barred = aggregator_row(host="site.test", is_active=True, is_logged_in=True)
    web = web_search_row(is_active=True, is_logged_in=True)
    await put(session_factory, barred, web, blacklist_row("aggregator", "site.test"))

    assert [a.id for a in await round_sources(session)] == [web.id]


async def test_the_list_and_the_card_show_the_mark(session, session_factory):
    barred = aggregator_row(host="site.test")
    clean = aggregator_row(host="other.test")
    await put(session_factory, barred, clean, blacklist_row("aggregator", "site.test"))

    listed = await list_aggregators_with_counts(session)
    _, _, value = await get_aggregator_detail(session, barred.id)

    assert [(row.host, marked) for row, _, marked in listed] == [
        ("site.test", True), ("other.test", False)
    ]
    assert value == "site.test"


async def test_aggregators_are_suggested_by_host(session, session_factory):
    """Подсказываются заведённые сайты; «Поиск по сети» — нет: хоста у него нет."""
    await put(session_factory, web_search_row(),
              aggregator_row(name="Работа", host="site.test"),
              aggregator_row(name="other.test", host="other.test"))

    assert await list_blacklist_candidates(session, "aggregator") == [
        {"value": "other.test", "label": "other.test", "sub": None},
        {"value": "site.test", "label": "Работа", "sub": "site.test"},
    ]
