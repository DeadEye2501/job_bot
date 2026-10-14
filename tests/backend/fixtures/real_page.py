"""Страница в настоящем браузере — для скриптов, которые исполняет сам браузер.

Подделка страницы ответила бы заготовленным, и поломка такого скрипта прошла бы
незамеченной. Нет на машине Chrome или Edge — проверка пропускается.
"""

from contextlib import asynccontextmanager

import pytest
from playwright.async_api import async_playwright

from adapters.browser import find_browser


@asynccontextmanager
async def page_with(html: str):
    """Страница с этой разметкой; браузер закрывается на выходе."""
    browser = find_browser()
    if browser is None:
        pytest.skip("на машине нет Chrome или Edge — скрипт исполнять негде")
    async with async_playwright() as playwright:
        launched = await playwright.chromium.launch(
            channel=browser.channel, executable_path=str(browser.executable) if browser.executable else None)
        one = await launched.new_page()
        await one.set_content(html)
        yield one
        await launched.close()
