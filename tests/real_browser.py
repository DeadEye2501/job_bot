"""Хозяин браузера на настоящем браузере машины — для проверок, которые подделка
подтвердить не может. Нет на машине браузера — проверка пропускается."""

from contextlib import asynccontextmanager

import pytest

from adapters.browser import BrowserHost, find_browser


@asynccontextmanager
async def real_host(profile_id: int = 1):
    """Хозяин с открытым профилем; браузер закрывается на выходе."""
    browser = find_browser()
    if browser is None:
        pytest.skip("на машине нет браузера на Chromium")
    host = BrowserHost(browser, always_visible=False, on_closed=lambda: None)
    try:
        await host.open_profile(profile_id)
        yield host
    finally:
        await host.close()
