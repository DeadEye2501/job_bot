"""Курсы от источника: успех, отказ источника, предел частоты."""

import httpx
import pytest

from adapters.exchange_rates import latest_rates
from tests.fakes.exchange_rates import RATES, serve_rates


async def test_the_rates_come_by_iso_code(monkeypatch):
    serve_rates(monkeypatch)
    assert await latest_rates() == RATES


async def test_an_error_result_is_not_taken_for_rates(monkeypatch):
    serve_rates(monkeypatch, httpx.Response(200, json={"result": "error", "error-type": "unsupported-code"}))
    with pytest.raises(ValueError, match="unsupported-code"):
        await latest_rates()


async def test_the_rate_limit_goes_up(monkeypatch):
    serve_rates(monkeypatch, httpx.Response(429))
    with pytest.raises(httpx.HTTPStatusError):
        await latest_rates()


async def test_a_success_without_rates_is_not_taken_for_rates(monkeypatch):
    serve_rates(monkeypatch, httpx.Response(200, json={"result": "success"}))
    with pytest.raises(ValueError):
        await latest_rates()
