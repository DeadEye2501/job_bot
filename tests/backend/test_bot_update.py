"""Скачивание обновления в месте прогона: ход идёт в полосу, занятое место — отказ."""

import asyncio
import sys

from backend.bot.update import download_update
from tests.fakes.github_release import APP, serve_newer


def _app_in(monkeypatch, tmp_path):
    """Приложение — `JobBot.exe` во временной папке, на GitHub релиз новее."""
    monkeypatch.setattr(sys, "executable", str(tmp_path / "JobBot.exe"))
    serve_newer(monkeypatch)


async def test_the_download_lies_next_to_the_app_and_its_way_reaches_the_bar(make_bot, monkeypatch, tmp_path):
    """Полоса показывает ход с первого мгновения, ещё до ответа GitHub, и до конца."""
    _app_in(monkeypatch, tmp_path)
    bot = await make_bot()
    steps = []
    bot.on_progress = lambda *step: steps.append(step)

    assert await download_update(bot) == "ok"

    assert (tmp_path / "JobBot.exe.new").read_bytes() == APP
    assert steps[0] == ("update", "Обновление", 0, 0)
    assert steps[-1] == ("update", "Обновление", len(APP), len(APP))


async def test_a_busy_slot_downloads_nothing(make_bot, monkeypatch, tmp_path):
    """Пока идёт прогон, скачивание не начинается: место прогона одно."""
    _app_in(monkeypatch, tmp_path)
    bot = await make_bot()
    bot.current_poll_task = asyncio.get_running_loop().create_future()

    assert await download_update(bot) == "busy"
    assert not (tmp_path / "JobBot.exe.new").exists()
