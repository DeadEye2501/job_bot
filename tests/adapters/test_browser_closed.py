"""Окно браузера агента, закрытое человеком, — это «Стоп», а не повод открыть его снова."""

import pytest

from adapters.browser import BrowserClosed
from tests.fakes.playwright import driven_host


async def test_a_window_the_person_closed_stops_the_work(monkeypatch):
    stops = []
    host, playwright = driven_host(monkeypatch, lambda: stops.append(1))
    await host.open_profile(1)

    playwright.contexts[0].fire("close")

    assert stops == [1]


async def test_a_window_closed_by_the_person_is_not_opened_again(monkeypatch):
    """Ни сразу — пока браузер ещё не сообщил о закрытии, а вкладок уже нет, —
    ни после: работа остановлена, и поднимать окно некому."""
    stops = []
    host, playwright = driven_host(monkeypatch, lambda: stops.append(1))
    await host.open_profile(1)
    playwright.contexts[0].pages.clear()

    for _ in range(2):
        with pytest.raises(BrowserClosed):
            await host.page()

    assert stops == [1] and len(playwright.contexts) == 1


async def test_the_next_work_opens_the_profile_again(monkeypatch):
    host, playwright = driven_host(monkeypatch)
    await host.open_profile(1)
    playwright.contexts[0].fire("close")

    await host.open_profile(1)

    assert len(playwright.contexts) == 2 and await host.page()


async def test_the_app_closing_its_own_profile_stops_nothing(monkeypatch):
    """Смена профиля и конец работы закрывают браузер сами — это не решение человека."""
    stops = []
    host, _ = driven_host(monkeypatch, lambda: stops.append(1))
    await host.open_profile(1)
    await host.open_profile(2)
    await host.close()

    assert stops == []
