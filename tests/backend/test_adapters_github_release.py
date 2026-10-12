"""Последний релиз приложения на GitHub: что из ответа API берётся и когда релиза нет."""

import httpx
import pytest

from adapters.github_release import Release, latest_release
from tests.fakes.github_release import release_answer, serve_latest


async def test_the_release_brings_its_tag_and_the_app_file(monkeypatch):
    serve_latest(monkeypatch, release_answer("v1.1.0"))

    assert await latest_release() == Release(
        tag="v1.1.0",
        url="https://github.com/DeadEye2501/job_bot/releases/download/v1.1.0/JobBot.exe",
        size=1024,
        sha256="ab" * 32,
    )


async def test_a_release_without_the_app_file_is_no_release(monkeypatch):
    """Обновиться не из чего — значит и обновления нет."""
    serve_latest(monkeypatch, release_answer("v1.1.0", asset="notes.txt"))

    assert await latest_release() is None


async def test_a_release_whose_file_has_no_checksum_is_no_release(monkeypatch):
    """Скачанное сверить будет не с чем, а ставить несверенный exe нельзя."""
    serve_latest(monkeypatch, release_answer("v1.1.0", digest=None))

    assert await latest_release() is None


async def test_no_release_at_all_is_no_release(monkeypatch):
    """Пока на GitHub не выложено ни одного релиза, API отвечает 404 — это «новой
    версии нет», а не беда связи."""
    serve_latest(monkeypatch, httpx.Response(404))

    assert await latest_release() is None


async def test_a_github_refusal_reaches_the_caller(monkeypatch):
    """Что сказать человеку о беде, решает зовущий: адаптер её не глушит."""
    serve_latest(monkeypatch, httpx.Response(503))

    with pytest.raises(httpx.HTTPStatusError):
        await latest_release()
