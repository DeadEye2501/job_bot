"""Браузер агента на настоящем браузере: страница не видит `navigator.webdriver`,
а вход, сохранённый в нём, переживает его закрытие."""

import time

from tests.real_browser import real_host


async def test_a_page_does_not_see_webdriver():
    """`navigator.webdriver` — признак, по которому сайт может узнать управляемый браузер."""
    async with real_host() as host:
        page = await host.page()
        driven = await page.evaluate("navigator.webdriver")

    assert driven is False


async def test_cookies_outlive_closing_the_browser():
    """Браузер закрывается выходом: погашенный, он не дописал бы куки на диск."""
    cookie = {"name": "session", "value": "kept", "url": "https://site.test/",
              "expires": time.time() + 3600}
    async with real_host() as host:
        await (await host.page()).context.add_cookies([cookie])

    async with real_host() as host:
        cookies = await (await host.page()).context.cookies("https://site.test/")

    assert [(c["name"], c["value"]) for c in cookies] == [("session", "kept")]
