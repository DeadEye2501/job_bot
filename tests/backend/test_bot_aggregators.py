"""Обход агрегаторов в боте: место прогона, режимы, человек, сроки, ручные действия."""

import asyncio

import pytest

from backend.agent.human_gate import HumanGate
from backend.bot import aggregators, loop
from backend.domain.apply_order import Way
from backend.models import Aggregator, BotMode
from backend.repository.aggregators import WEB_SEARCH_NAME
from backend.repository.bot_mode import write_mode
from tests.dbio import all_rows, put
from tests.factories import vacancy_row
from tests.factories_aggregators import aggregator_row
from tests.fakes.agent import kit_for, scripted
from tests.fakes.browser import FakeBrowser


@pytest.fixture
def agent(monkeypatch):
    """Агент доступен, набор — по сценарию; срок человека задаёт тест."""

    def install(bot, steps, *, human_limit=None):
        if human_limit is not None:
            bot.human_gate = HumanGate(lambda kind, host: None, lambda: None, limit_sec=human_limit)
        kit = kit_for(bot.ingestion, browser=FakeBrowser(), gate=bot.human_gate,
                      run_session=scripted(steps))
        monkeypatch.setattr(aggregators, "_kit", lambda _bot: kit)
        monkeypatch.setattr(aggregators, "aggregators_available", lambda _bot: None)
        return kit

    return install


@pytest.fixture
async def sites(session_factory):
    """Один включённый агрегатор со входом и выключенный «Поиск по сети»."""
    site = aggregator_row(host="site.test", is_active=True, is_logged_in=True)
    await put(session_factory, site, aggregator_row(name=WEB_SEARCH_NAME, host=None))
    return site


async def _settled(bot):
    """С потолком: не освободись место, тест упадёт, а не повиснет."""

    async def freed():
        while bot.current_poll_task is not None:
            await asyncio.sleep(0)

    await asyncio.wait_for(freed(), 5)


def _hold(release):
    async def step(tools):
        await release.wait()
        await tools["finish"](result="done")
    return step


async def _done(tools):
    await tools["finish"](result="done")


async def test_a_full_tick_launches_the_round_and_the_next_tick_finds_it_busy(
    make_bot, sites, agent
):
    bot = await make_bot()
    release = asyncio.Event()
    kit = agent(bot, [_hold(release)])

    await loop._tick(bot, BotMode.FULL)
    await asyncio.sleep(0)
    running = bot.current_poll_task

    await loop._tick(bot, BotMode.FULL)

    assert running is not None and bot.current_poll_task is not None
    release.set()
    await _settled(bot)
    assert len(kit.run_session.plans) == 1


async def test_dm_only_runs_no_round(make_bot, sites, agent):
    bot = await make_bot()
    kit = agent(bot, [_done])

    await loop._tick(bot, BotMode.DM_ONLY)

    assert bot.current_poll_task is None and kit.run_session.plans == []


async def test_an_unavailable_agent_skips_the_round_quietly(make_bot, sites, agent, monkeypatch):
    bot = await make_bot()
    kit = agent(bot, [_done])
    monkeypatch.setattr(aggregators, "aggregators_available", lambda _bot: "нужен Claude Code")

    await aggregators.launch_round(bot)

    assert bot.current_poll_task is None and kit.run_session.plans == []


async def test_entering_off_puts_the_round_out_and_closes_the_browser(make_bot, sites, agent):
    bot = await make_bot()
    kit = agent(bot, [_hold(asyncio.Event())])
    await aggregators.launch_round(bot)
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    await loop._on_mode_switch(bot, BotMode.FULL, BotMode.OFF)
    await _settled(bot)

    assert "close" in kit.browser.calls


async def test_the_window_hears_when_a_person_is_needed_and_when_they_are_done(
    make_bot, sites, agent
):
    bot = await make_bot()
    heard = []
    bot.on_human_needed = lambda kind, host: heard.append((kind, host))
    bot.on_human_resolved = lambda: heard.append("resolved")

    async def step(tools):
        await tools["need_human"](kind="captcha")
        await tools["finish"](result="done")

    agent(bot, [step])
    await aggregators.launch_round(bot)
    async def asked():
        while not heard:
            await asyncio.sleep(0)

    await asyncio.wait_for(asked(), 5)

    aggregators.human_done(bot)
    await _settled(bot)

    assert heard == [("captcha", "site.test"), "resolved"]


async def test_an_expired_wait_drops_the_round_and_tells_the_window(
    make_bot, sites, agent, session_factory
):
    bot = await make_bot()
    notes = []
    bot.on_round_note = notes.append

    async def step(tools):
        await tools["need_human"](kind="captcha")

    agent(bot, [step], human_limit=0.01)
    await aggregators.launch_round(bot)
    await _settled(bot)

    assert notes == [aggregators.HUMAN_TIMEOUT_NOTE]
    assert all(a.last_run_at is None for a in await all_rows(session_factory, Aggregator))


async def test_a_manual_application_is_refused_in_off_and_while_busy(
    make_bot, agent, session_factory, busy_slot
):
    bot = await make_bot()
    vacancy = vacancy_row()
    await put(session_factory, vacancy)
    agent(bot, [])
    way = Way("form", "https://company.test/apply", None)

    assert await aggregators.apply_via_agent(bot, vacancy.id, way) == "off"
    async with session_factory() as session:
        async with session.begin():
            await write_mode(session, BotMode.DM_ONLY)
    busy_slot(bot)
    assert await aggregators.apply_via_agent(bot, vacancy.id, way) == "busy"


async def test_a_stop_during_a_single_run_is_a_cancellation(make_bot, sites, agent):
    bot = await make_bot()
    agent(bot, [_hold(asyncio.Event())])
    running = asyncio.create_task(aggregators.run_aggregator_now(bot, sites.id))
    async def started():
        while not bot.current_poll_task:
            await asyncio.sleep(0)

    await asyncio.wait_for(started(), 5)
    await asyncio.sleep(0)

    bot.cancel_current_poll()

    assert await running == "cancelled"


async def test_after_an_expired_run_the_next_one_starts_with_a_clean_gate(make_bot, sites, agent):
    """Без сброса первая же сессия следующего запуска получила бы «срок вышел»."""
    bot = await make_bot()

    async def wait(tools):
        await tools["need_human"](kind="captcha")

    agent(bot, [wait, _done], human_limit=0.01)

    assert await aggregators.run_aggregator_now(bot, sites.id) == "human_timeout"
    assert await aggregators.run_aggregator_now(bot, sites.id) == "ok"


async def test_deleting_an_aggregator_waits_for_a_free_slot_and_takes_its_profile(
    make_bot, session_factory, busy_slot, monkeypatch
):
    bot = await make_bot()
    site = aggregator_row(host="site.test")
    await put(session_factory, site)
    removed = []
    monkeypatch.setattr(aggregators, "remove_profile", removed.append)

    busy_slot(bot)
    assert await aggregators.delete_aggregator(bot, site.id) == "busy"
    bot.current_poll_task = None

    assert await aggregators.delete_aggregator(bot, site.id) == "ok"
    assert removed == [site.id] and await all_rows(session_factory, Aggregator) == []
