"""Запуск браузера агента, сорвавшийся до подключения, не оставляет браузера на профиле."""

import asyncio

import pytest
from playwright.async_api import Error as PlaywrightError

from tests.fakes.playwright import driven_host
from tests.waiting import wait_until


async def test_a_browser_that_failed_to_connect_is_put_out(monkeypatch):
    """Брошенный, он держал бы профиль, а закрытие хозяина падало бы на нём."""
    host, playwright = driven_host(monkeypatch)
    playwright.refusal = PlaywrightError("connect ECONNREFUSED")

    with pytest.raises(PlaywrightError):
        await host.open_profile(1)

    assert playwright.driven[0].terminated
    await host.close()


async def test_a_stop_while_starting_leaves_the_profile_free(monkeypatch):
    host, playwright = driven_host(monkeypatch)
    playwright.connecting = asyncio.Event()
    starting = asyncio.create_task(host.open_profile(1))
    await wait_until(lambda: playwright.driven)

    starting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await starting
    playwright.connecting = None
    await host.open_profile(1)

    first, second = playwright.driven
    assert first.terminated and second.returncode is None and await host.page()
