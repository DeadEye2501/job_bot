"""Подделка HTTP для адаптеров со своим сборщиком клиента: настоящий `httpx`
поверх заготовленных ответов.

Отличие от `tests/fakes/llm.py`: там подделка поставщика модели, а здесь общий
приём для адаптеров страниц и релизов — подменить им сборку клиента. Правила
ответов у них одни, и берутся они у того же обработчика.
"""

import httpx

from tests.fakes.llm import handler


def serve(monkeypatch, make_client: str, routes: dict) -> None:
    """Подменить сборку клиента адаптера; `make_client` — путь к сборщику.

    Разбор ответов остаётся боевым. Сеть тестов не заперта, и без подмены
    адаптер ушёл бы в живую сеть.
    """

    def _client() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(handler(routes, [], httpx)))

    monkeypatch.setattr(make_client, _client)
