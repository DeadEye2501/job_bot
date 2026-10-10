"""Клиент, которым ходят за чужой веб-страницей.

Отдельно от `site_home` и `telegraph`: те разбирают каждый свою страницу, а
сходить за ней у них одно дело, и различается оно только сроком ожидания и
тем, кем назваться сайту.
"""

import httpx


def page_client(timeout_sec: float, user_agent: str) -> httpx.AsyncClient:
    """Клиент к странице. Переходы разрешены: страницы часто уводят на свой адрес."""
    return httpx.AsyncClient(
        timeout=timeout_sec,
        follow_redirects=True,
        headers={"User-Agent": user_agent},
    )
