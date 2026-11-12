"""Обновление кэша курсов: раз в сутки, без сети — прежний кэш, после неудачи —
не чаще раза в час."""

from datetime import timedelta

import httpx
from sqlalchemy import delete

from backend.flows import rates_refresh
from backend.flows.rates_refresh import RatesRefresh
from backend.models import CurrencyRate
from backend.repository.currency_rates import load_rates
from backend.telegram_time import utc_now
from tests.dbio import put
from tests.fakes.exchange_rates import rates_answer, serve_rates


async def _cached(session_factory, age: timedelta, **rates: float) -> None:
    """Кэш ровно из этих курсов: засеянный обвязкой сносится."""
    async with session_factory() as session:
        async with session.begin():
            await session.execute(delete(CurrencyRate))
    await put(session_factory, *[
        CurrencyRate(code=code, per_usd=rate, fetched_at=utc_now() - age) for code, rate in rates.items()
    ])


async def _rates(session_factory) -> dict[str, float]:
    async with session_factory() as session:
        return await load_rates(session)


async def test_a_fresh_cache_is_not_asked_again(session_factory, monkeypatch):
    await _cached(session_factory, timedelta(hours=1), USD=1.0, RUB=90.0)
    serve_rates(monkeypatch, rates_answer({"USD": 1.0, "RUB": 70.0}))

    await RatesRefresh(session_factory).run()

    assert await _rates(session_factory) == {"$": 1.0, "₽": 90.0}


async def test_an_old_cache_is_replaced_by_sign(session_factory, monkeypatch):
    await _cached(session_factory, timedelta(days=2), USD=1.0, RUB=90.0)
    serve_rates(monkeypatch, rates_answer({"USD": 1.0, "RUB": 70.0, "EUR": 0.9, "JPY": 150.0}))

    await RatesRefresh(session_factory).run()

    assert await _rates(session_factory) == {"$": 1.0, "₽": 70.0, "€": 0.9}


async def test_without_the_network_the_old_cache_stays(session_factory, monkeypatch):
    await _cached(session_factory, timedelta(days=2), USD=1.0, RUB=90.0)
    serve_rates(monkeypatch, httpx.ConnectError("сети нет"))

    await RatesRefresh(session_factory).run()

    assert await _rates(session_factory) == {"$": 1.0, "₽": 90.0}


async def test_a_code_missing_from_the_answer_keeps_its_rate(session_factory, monkeypatch):
    await _cached(session_factory, timedelta(days=2), USD=1.0, RUB=90.0, GEL=2.7)
    serve_rates(monkeypatch, rates_answer({"USD": 1.0, "RUB": 70.0}))

    await RatesRefresh(session_factory).run()

    assert await _rates(session_factory) == {"$": 1.0, "₽": 70.0, "₾": 2.7}


async def test_a_code_left_behind_does_not_keep_the_cache_old(session_factory, monkeypatch):
    await _cached(session_factory, timedelta(hours=1), USD=1.0, RUB=90.0)
    await put(session_factory, CurrencyRate(code="GEL", per_usd=2.7, fetched_at=utc_now() - timedelta(days=5)))
    serve_rates(monkeypatch, rates_answer({"USD": 1.0, "RUB": 70.0}))

    await RatesRefresh(session_factory).run()

    assert (await _rates(session_factory))["₽"] == 90.0


def _counted_failures(monkeypatch) -> list[int]:
    asked: list[int] = []

    async def latest_rates():
        asked.append(1)
        raise httpx.ConnectError("сети нет")

    monkeypatch.setattr(rates_refresh.exchange_rates, "latest_rates", latest_rates)
    return asked


async def test_after_a_failure_the_source_is_not_asked_again_within_the_hour(session_factory, monkeypatch):
    await _cached(session_factory, timedelta(days=2), USD=1.0)
    asked = _counted_failures(monkeypatch)
    refresh = RatesRefresh(session_factory)

    await refresh.run()
    await refresh.run()

    assert len(asked) == 1


async def test_an_hour_after_a_failure_the_source_is_asked_again(session_factory, monkeypatch):
    await _cached(session_factory, timedelta(days=2), USD=1.0)
    asked = _counted_failures(monkeypatch)
    refresh = RatesRefresh(session_factory)
    start = utc_now()

    monkeypatch.setattr(rates_refresh, "utc_now", lambda: start)
    await refresh.run()
    monkeypatch.setattr(rates_refresh, "utc_now", lambda: start + timedelta(hours=1, minutes=1))
    await refresh.run()

    assert len(asked) == 2


async def test_an_answer_without_our_currencies_waits_the_hour_too(session_factory, monkeypatch):
    await _cached(session_factory, timedelta(days=2), USD=1.0)
    asked: list[int] = []

    async def latest_rates():
        asked.append(1)
        return {"JPY": 150.0}

    monkeypatch.setattr(rates_refresh.exchange_rates, "latest_rates", latest_rates)
    refresh = RatesRefresh(session_factory)

    await refresh.run()
    await refresh.run()

    assert len(asked) == 1
