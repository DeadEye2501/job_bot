"""Мир откликателя: что доступно прямо сейчас."""

import time

from backend.applying.result import SiteClosed
from backend.applying.world import learn, read_world, vacancy_facts, ways_in
from backend.domain.apply_order import KnownSite, World
from tests.dbio import put
from tests.factories import hr_row, vacancy_row
from tests.factories_aggregators import aggregator_row


def _world(**over) -> World:
    return World(**{"telegram_open": True, "mail_ready": True, "agent_ready": True,
                    "sites": [], "closed_sites": set(), **over})


async def _facts(session_factory, **vacancy):
    row = vacancy_row(**vacancy)
    await put(session_factory, row)
    async with session_factory() as session:
        return await vacancy_facts(session, row.id)


async def test_an_hr_known_by_number_alone_is_written_to_by_number(session_factory):
    hr = hr_row(telegram_username=None, telegram_user_id=4242)
    await put(session_factory, hr)
    assert (await _facts(session_factory, hr_id=hr.id)).hr_handle == "4242"


async def test_an_hr_without_an_address_is_no_telegram_way(session_factory):
    hr = hr_row(telegram_username=None, telegram_user_id=None)
    await put(session_factory, hr)
    assert (await _facts(session_factory, hr_id=hr.id)).hr_handle is None


async def test_a_vacancy_from_an_aggregator_knows_its_site(session_factory):
    site = aggregator_row(host="site.test")
    await put(session_factory, site)
    facts = await _facts(session_factory, source_aggregator_id=site.id,
                         source_key="vacancy/1", source_url="https://site.test/vacancy/1")
    assert facts.source_site == KnownSite(site.id, "site.test")


async def test_a_deleted_vacancy_has_no_ways(kit):
    assert await ways_in(kit, _world(), 999) == []


def test_a_closed_site_is_learned_for_the_rest_of_the_run():
    world = _world()
    learn(world, SiteClosed(3))
    assert world.closed_sites == {3}


async def test_a_ban_in_the_store_closes_telegram(kit):
    await kit.pipeline.rs.set_app("flood_wait_until_ts", str(time.time() + 600))
    assert not (await read_world(kit)).telegram_open


async def test_a_past_ban_leaves_telegram_open(kit):
    await kit.pipeline.rs.set_app("flood_wait_until_ts", str(time.time() - 1))
    assert (await read_world(kit)).telegram_open
