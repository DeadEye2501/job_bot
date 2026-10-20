"""Скачивание обновления в месте прогона: ход идёт в полосу, занятое место — отказ."""

import asyncio
import sys

import pytest

from backend.bot.update import download_update
from tests.fakes.github_release import APP, serve_newer


def _app_in(monkeypatch, tmp_path):
    """Приложение — `JobBot.exe` во временной папке, на GitHub релиз новее."""
    monkeypatch.setattr(sys, "executable", str(tmp_path / "JobBot.exe"))
    serve_newer(monkeypatch)


@pytest.fixture
def handed(monkeypatch):
    """Кому отдано скачанное: путь, с которым запущена копия-подменщик."""
    given = []
    monkeypatch.setattr("backend.updater.launch_updater", given.append)
    return given


async def test_the_download_lies_next_to_the_app_and_goes_to_the_copy(make_bot, monkeypatch, tmp_path, handed):
    """Полоса показывает ход с первого мгновения, ещё до ответа GitHub, и до конца;
    скачанное и сверенное уходит копии-подменщику."""
    _app_in(monkeypatch, tmp_path)
    bot = await make_bot()
    steps = []
    bot.on_progress = lambda *step: steps.append(step)

    assert await download_update(bot) == "ok"

    assert (tmp_path / "JobBot.exe.new").read_bytes() == APP
    assert steps[0] == ("update", "Скачивание обновления", 0, 0)
    assert steps[-1] == ("update", "Скачивание обновления", len(APP), len(APP))
    assert handed == [tmp_path / "JobBot.exe.new"]


async def test_a_copy_that_did_not_start_is_named_as_such(make_bot, monkeypatch, tmp_path, caplog):
    """Файл скачан и сверен, а копию запустить не вышло: это не «не скачалось», и
    человеку говорят то, что случилось; трассировка — в журнале."""
    _app_in(monkeypatch, tmp_path)

    def broken(new):
        raise OSError("нет места")

    monkeypatch.setattr("backend.updater.launch_updater", broken)
    bot = await make_bot()

    assert await download_update(bot) == "handoff_failed"
    assert any("копию" in r.getMessage() for r in caplog.records)


async def test_a_busy_slot_downloads_nothing(make_bot, monkeypatch, tmp_path, handed):
    """Пока идёт прогон, скачивание не начинается: место прогона одно."""
    _app_in(monkeypatch, tmp_path)
    bot = await make_bot()
    bot.current_poll_task = asyncio.get_running_loop().create_future()

    assert await download_update(bot) == "busy"
    assert not (tmp_path / "JobBot.exe.new").exists() and handed == []


@pytest.fixture(autouse=True)
def windows_update_capability(monkeypatch):
    """Здесь проверяется Windows-протокол скачивания, а не выбор платформы."""
    monkeypatch.setattr("backend.update_download.supports_updates", lambda: True)
    monkeypatch.setattr("backend.update_download.can_install_update", lambda: True)
    monkeypatch.setattr("backend.updater.can_install_update", lambda: True)
