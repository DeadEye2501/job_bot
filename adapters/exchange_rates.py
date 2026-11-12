"""Курсы валют за 1 USD от open.er-api.com: бесплатно, без ключа, раз в сутки.

Отличие от `adapters/web_page`: тот только собирает клиент страниц, а здесь
знают форму ответа источника курсов. Клиент берётся у него же.
"""

import httpx

from adapters.web_page import page_client

LATEST = "https://open.er-api.com/v6/latest/USD"
# Короткий срок: без сети запрос ждёт его при каждой попытке обновить курсы.
_TIMEOUT_SEC = 5.0
_USER_AGENT = "JobBot-rates"


def make_client() -> httpx.AsyncClient:
    return page_client(_TIMEOUT_SEC, _USER_AGENT)


async def latest_rates() -> dict[str, float]:
    """Курсы по кодам ISO за 1 USD.

    Беда сети и отказ источника уходят наверх; ответ не той формы — `ValueError`:
    что делать без курсов, решает зовущий.
    """
    async with make_client() as client:
        response = await client.get(LATEST)
    response.raise_for_status()
    body = response.json()
    if body.get("result") != "success" or not isinstance(body.get("rates"), dict):
        raise ValueError(f"курсы не пришли: {body.get('error-type') or body.get('result')}")
    return {code: float(rate) for code, rate in body["rates"].items()}
