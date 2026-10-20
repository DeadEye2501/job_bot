"""Скачивание обновления: файл ложится, только если сошёлся с релизом; иначе его нет."""

import asyncio

import httpx
import pytest

from backend.app_version import VERSION
from backend.update_download import download_update
from tests.fakes.github_release import APP, release_answer, serve_latest, serve_newer

MB = 1024 * 1024


@pytest.fixture
def target(tmp_path):
    return tmp_path / "JobBot.exe.new"


def _quiet(got, total):
    """Ход, на который тест не смотрит."""


async def test_a_matching_file_is_kept(monkeypatch, target):
    serve_newer(monkeypatch)

    assert await download_update(target, _quiet) == "ok"
    assert target.read_bytes() == APP


async def test_the_way_is_reported_each_megabyte_and_once_at_the_end(monkeypatch, target):
    """Чаще окну незачем, а кольцо вестей переполнилось бы; конец — ровно один раз."""
    content = b"\0" * (2 * MB)
    serve_newer(monkeypatch, content=content)
    steps = []

    await download_update(target, lambda got, total: steps.append((got, total)))

    assert [got // MB for got, _ in steps] == [1, 2]
    assert steps[-1] == (2 * MB, 2 * MB)


async def test_no_newer_release_downloads_nothing(monkeypatch, target):
    serve_latest(monkeypatch, release_answer(f"v{VERSION}"))

    assert await download_update(target, _quiet) == "no_update"
    assert not target.exists()


async def test_a_file_that_does_not_match_the_release_is_removed(monkeypatch, target):
    """Несверенный exe ставить нельзя: не та сумма — файла нет."""
    serve_newer(monkeypatch, digest="sha256:" + "00" * 32)

    assert await download_update(target, _quiet) == "broken"
    assert not target.exists()


@pytest.mark.parametrize("served", [httpx.ReadError("обрыв"), httpx.Response(404)])
async def test_a_failed_download_leaves_no_half_file(monkeypatch, target, served):
    serve_newer(monkeypatch, served=served)

    with pytest.raises(httpx.HTTPError):
        await download_update(target, _quiet)
    assert not target.exists()


async def test_a_stopped_download_leaves_no_half_file(monkeypatch, target):
    """«Стоп» гасит задачу посреди потока — недокачанный exe не остаётся."""
    serve_newer(monkeypatch, content=b"\0" * (2 * MB))

    def stop_at_first_megabyte(got, total):
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await download_update(target, stop_at_first_megabyte)
    assert not target.exists()


async def test_a_file_held_by_the_system_does_not_spoil_the_outcome(monkeypatch, target, caplog):
    """Свежий файл держит антивирус — удалить не вышло, но исход остаётся своим,
    а след — в журнале; лишний файл уберёт следующий запуск."""
    serve_newer(monkeypatch, digest="sha256:" + "00" * 32)

    def held(self, missing_ok=False):
        raise PermissionError("файл занят")

    monkeypatch.setattr(type(target), "unlink", held)

    assert await download_update(target, _quiet) == "broken"
    assert any("не удалось убрать" in r.getMessage() for r in caplog.records)


@pytest.fixture(autouse=True)
def windows_update_capability(monkeypatch):
    """Здесь проверяется Windows-протокол скачивания, а не выбор платформы."""
    monkeypatch.setattr("backend.update_download.supports_updates", lambda: True)
    monkeypatch.setattr("backend.update_download.can_install_update", lambda: True)
    monkeypatch.setattr("backend.updater.can_install_update", lambda: True)
