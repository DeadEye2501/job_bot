"""Обход агрегаторов в боте: место прогона, режимы, человек, сроки, ручные действия."""

import asyncio

import pytest

from backend.bot import aggregators, loop, slot, work
from backend.bot.turn import launch_turn
from backend.models import Aggregator, BotMode
from tests.backend.fixtures.bot import slot_freed, switch_to
from tests.dbio import all_rows, put
from tests.factories import blacklist_row
from tests.factories_aggregators import aggregator_row, web_search_row
from tests.fakes.agent import (
    captcha_step,
    finish_step,
    kit_for,
    login_step,
    scripted,
    silent_gate,
)
from tests.fakes.browser import FakeBrowser
from tests.waiting import wait_until


@pytest.fixture
def agent(monkeypatch):
    """Агент доступен, набор — по сценарию; срок человека задаёт тест."""

    def install(bot, steps, *, human_limit=None):
        if human_limit is not None:
            bot.human_gate = silent_gate(human_limit)
        kit = kit_for(bot.ingestion, browser=FakeBrowser(), gate=bot.human_gate,
                      run_session=scripted(steps))
        monkeypatch.setattr(work, "_kit", lambda _bot: kit)
        monkeypatch.setattr(aggregators, "aggregators_available", lambda _bot: None)
        return kit

    return install


@pytest.fixture
async def sites(session_factory):
    """Один включённый агрегатор со входом и выключенный «Поиск по сети»."""
    site = aggregator_row(host="site.test", is_active=True, is_logged_in=True)
    await put(session_factory, site, web_search_row())
    return site


def _hold(release):
    async def step(tools):
        await release.wait()
        await tools["finish"](result="done")
    return step


async def test_a_full_tick_launches_the_round_and_the_next_tick_finds_it_busy(
    make_bot, sites, agent, session_factory
):
    bot = await make_bot()
    await switch_to(session_factory, BotMode.FULL)
    release = asyncio.Event()
    kit = agent(bot, [_hold(release)])

    await loop._tick(bot, BotMode.FULL)
    await asyncio.sleep(0)
    running = bot.current_poll_task

    await loop._tick(bot, BotMode.FULL)

    assert running is not None and bot.current_poll_task is not None
    release.set()
    await slot_freed(bot)
    assert len(kit.run_session.plans) == 1


async def test_off_during_the_channel_poll_lets_the_started_turn_finish(
    make_bot, sites, agent, session_factory, monkeypatch
):
    """Off запрещает автоматике следующий запуск, но не отменяет начатого: оборот
    уже пошёл — каналы, затем агрегаторы, — и дорабатывает целиком."""
    bot = await make_bot()
    await switch_to(session_factory, BotMode.FULL)
    kit = agent(bot, [finish_step()])

    async def poll_then_off():
        await switch_to(session_factory, BotMode.OFF)

    bot.ingestion.poll_active_channels = poll_then_off
    await loop._tick(bot, BotMode.FULL)
    await slot_freed(bot)

    assert len(kit.run_session.plans) == 1


async def test_stop_pressed_during_the_channel_poll_stops_the_whole_turn(
    make_bot, sites, agent, session_factory
):
    """«Стоп» гасит оборот целиком: погашенный опрос каналов не доходит до
    агрегаторов, хотя бот при этом жив и работает дальше."""
    bot = await make_bot()
    await switch_to(session_factory, BotMode.FULL)
    kit = agent(bot, [finish_step()])
    polling = asyncio.Event()

    async def poll_forever():
        polling.set()
        await asyncio.Event().wait()

    bot.ingestion.poll_active_channels = poll_forever
    await loop._tick(bot, BotMode.FULL)
    await polling.wait()
    slot.cancel_current_poll(bot)
    await slot_freed(bot)

    assert bot.launched_task.result()[0] == "cancelled" and kit.run_session.plans == []


async def test_entering_off_lets_the_channel_poll_finish(make_bot):
    """Off ничего не отменяет: опрос каналов дорабатывает свой оборот."""
    bot = await make_bot()
    release = asyncio.Event()
    polling = asyncio.create_task(slot.run_in_slot(bot, release.wait, "poll cycle"))
    await asyncio.sleep(0)

    await loop._on_mode_switch(bot, BotMode.FULL, BotMode.OFF)
    release.set()

    assert (await polling)[0] == "ok"


async def test_dm_only_runs_no_round(make_bot, sites, agent):
    bot = await make_bot()
    kit = agent(bot, [finish_step()])

    await loop._tick(bot, BotMode.DM_ONLY)

    assert bot.current_poll_task is None and kit.run_session.plans == []


async def test_an_unavailable_agent_skips_the_round_quietly(make_bot, sites, agent, monkeypatch):
    bot = await make_bot()
    kit = agent(bot, [finish_step()])
    monkeypatch.setattr(aggregators, "aggregators_available", lambda _bot: "нужен Claude Code")

    await aggregators.seek_all(bot, kit)

    assert kit.run_session.plans == [] and kit.browser.calls == []


async def test_entering_off_lets_the_running_round_finish(make_bot, sites, agent):
    """Off ничего не отменяет: идущий обход агрегаторов дорабатывает. Остановить
    его — дело кнопки «Стоп»."""
    bot = await make_bot()
    release = asyncio.Event()
    kit = agent(bot, [_hold(release)])
    launch_turn(bot, "turn")
    await wait_until(lambda: kit.run_session.plans)

    await loop._on_mode_switch(bot, BotMode.FULL, BotMode.OFF)
    await asyncio.sleep(0)

    assert bot.launched_task is not None and not bot.launched_task.done()
    release.set()
    await slot_freed(bot)
    assert kit.run_session.plans and bot.launched_task.result()[0] == "ok"


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
    launch_turn(bot, "turn")
    await wait_until(lambda: heard)

    aggregators.human_done(bot)
    await slot_freed(bot)

    assert heard == [("captcha", "site.test"), "resolved"]


async def test_an_expired_wait_drops_the_round_and_tells_the_window(
    make_bot, sites, agent, session_factory
):
    bot = await make_bot()
    notes = []
    bot.on_round_note = notes.append

    agent(bot, [captcha_step()], human_limit=0.01)
    launch_turn(bot, "turn")
    await slot_freed(bot)

    assert notes == [work.HUMAN_TIMEOUT_NOTE]
    assert all(a.last_run_at is None for a in await all_rows(session_factory, Aggregator))


async def test_a_stop_during_a_single_run_is_a_cancellation(make_bot, sites, agent):
    bot = await make_bot()
    agent(bot, [_hold(asyncio.Event())])
    running = asyncio.create_task(aggregators.run_aggregator_now(bot, sites.id))
    await wait_until(lambda: bot.current_poll_task)
    await asyncio.sleep(0)

    bot.cancel_current_poll()

    assert await running == "cancelled"


async def test_after_an_expired_run_the_next_one_starts_with_a_clean_gate(make_bot, sites, agent):
    """Без сброса первая же сессия следующего запуска получила бы «срок вышел»."""
    bot = await make_bot()

    agent(bot, [captcha_step(), finish_step()], human_limit=0.01)

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


async def test_a_login_the_agent_did_not_confirm_is_not_reported_as_done(make_bot, sites, agent):
    bot = await make_bot()
    agent(bot, [login_step(False)])

    assert await aggregators.login_aggregator(bot, sites.id) == "not_logged_in"


async def test_a_login_opens_the_profile_for_a_human(make_bot, sites, agent):
    """Входит человек руками, и браузер для входа открыт без пометки «управляется
    программой»: с ней вход Google отказывает."""
    bot = await make_bot()
    kit = agent(bot, [login_step(True)])

    await aggregators.login_aggregator(bot, sites.id)

    assert kit.browser.as_person is True


async def test_the_login_check_is_not_told_to_call_a_person(make_bot, sites, agent):
    """Проверка входа идёт, когда человек уже закрыл окно, и звать его ей нечем:
    правила про зов человека в её наставлении нет."""
    bot = await make_bot()
    kit = agent(bot, [login_step(True)])

    await aggregators.login_aggregator(bot, sites.id)

    (plan,) = kit.run_session.plans
    assert "need_human" not in plan.system_prompt


async def test_a_login_window_left_open_is_not_called_a_captcha(make_bot, sites, agent):
    bot = await make_bot()
    kit = agent(bot, [])
    kit.browser.closes = False

    assert await aggregators.login_aggregator(bot, sites.id) == "login_timeout"


@pytest.fixture
def sought(monkeypatch):
    """Источники, на которых прошёл поиск."""
    names = []

    async def seek(kit, source):
        names.append(source.name)

    monkeypatch.setattr(aggregators, "seek_source", seek)
    return names


async def test_a_run_started_by_hand_runs_in_off_too(make_bot, sites, agent, sought, session_factory):
    """Режим — про автоматику: обход, запущенный человеком, отрабатывает и в Off."""
    bot = await make_bot()
    agent(bot, [])
    await switch_to(session_factory, BotMode.OFF)

    assert await aggregators.run_aggregator_now(bot, sites.id) == "ok"
    assert sought == [sites.name]


async def test_a_blacklisted_site_is_neither_run_nor_logged_into(
    make_bot, sites, agent, session_factory
):
    """Ручной обход и вход тоже не трогают сайт из отсева: отметку снимают, а не обходят."""
    bot = await make_bot()
    kit = agent(bot, [finish_step(), finish_step()])
    await put(session_factory, blacklist_row("aggregator", "site.test"))

    assert await aggregators.run_aggregator_now(bot, sites.id) == "blacklisted"
    assert await aggregators.login_aggregator(bot, sites.id) == "blacklisted"
    assert kit.run_session.plans == []


async def test_the_switch_over_all_aggregators_keeps_the_round_from_starting(
    make_bot, sites, agent
):
    """Общий выключатель гасит обход целиком; строки при этом остаются включёнными."""
    bot = await make_bot()
    kit = agent(bot, [finish_step()])
    await bot.rs.set_app("aggregators_enabled", "false")

    await aggregators.seek_all(bot, kit)

    assert kit.run_session.plans == [] and kit.browser.calls == []


async def test_the_switch_over_all_aggregators_leaves_a_manual_run_alone(
    make_bot, sites, agent
):
    bot = await make_bot()
    agent(bot, [finish_step()])
    await bot.rs.set_app("aggregators_enabled", "false")

    assert await aggregators.run_aggregator_now(bot, sites.id) == "ok"
