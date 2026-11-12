"""Подделка источника курсов поверх подставного транспорта.

Подменяется сборка клиента (`adapters.exchange_rates.make_client`), разбор
ответа остаётся боевым. Сеть тестов не заперта, и без подмены каждая загрузка
слепков конвейера ушла бы на живой open.er-api.com.
"""

from urllib.parse import urlsplit

import httpx

from adapters.exchange_rates import LATEST
from tests.fakes.http import serve

RATES = {"USD": 1.0, "RUB": 80.0, "EUR": 0.9, "AMD": 400.0, "KZT": 500.0, "GEL": 2.5}


def rates_answer(rates: dict[str, float] | None = None) -> httpx.Response:
    return httpx.Response(200, json={"result": "success", "rates": RATES if rates is None else rates})


def serve_rates(monkeypatch, prepared: httpx.Response | BaseException | None = None) -> None:
    """Источник отвечает заготовленным; исключение — сеть не дотянулась."""
    answer = rates_answer() if prepared is None else prepared
    serve(monkeypatch, "adapters.exchange_rates.make_client", {("GET", urlsplit(LATEST).path): answer})
