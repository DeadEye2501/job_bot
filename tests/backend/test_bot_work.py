"""Работа с набором агента в месте прогона: остановки, которые снимают её целиком."""

import asyncio

from backend.agent.stops import ResumeMissing
from backend.bot import work
from tests.fakes.agent import work_kit


async def test_a_missing_resume_stops_the_work_and_names_the_site(make_bot, monkeypatch):
    bot = await make_bot()
    notes = []
    bot.on_round_note = notes.append
    monkeypatch.setattr(work, "_kit", work_kit)

    async def apply(kit):
        raise ResumeMissing("site.test")

    assert await work.in_slot(bot, apply, "apply") == "resume_missing"
    assert notes == ["Выбранное резюме не найдено на site.test — обновите список резюме"]


async def test_a_window_closed_mid_application_ends_only_that_application(make_bot, monkeypatch):
    bot = await make_bot()
    stops = []
    monkeypatch.setattr(work.slot, "cancel_current_poll", stops.append)
    kit = work_kit(bot)
    kit.window_closed = asyncio.Event()

    work.window_closed(bot, kit)

    assert kit.window_closed.is_set() and stops == []


async def test_a_window_closed_outside_an_application_stops_the_work(make_bot, monkeypatch):
    bot = await make_bot()
    stops = []
    monkeypatch.setattr(work.slot, "cancel_current_poll", stops.append)

    work.window_closed(bot, work_kit(bot))

    assert stops == [bot]
