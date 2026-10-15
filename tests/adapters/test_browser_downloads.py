"""Браузер агента не скачивает файлов: всякая загрузка обрывается самим браузером.

Проверяется настоящим браузером: запрет живёт в настройках запуска, и подделка
браузера подтвердила бы только то, что настройка передана, а не то, что файл не
лёг на диск. Нет на машине Chrome или Edge — проверка пропускается.
"""

import pytest
from playwright.async_api import async_playwright

from adapters.browser import context_options, find_browser


async def test_a_file_the_page_offers_is_not_saved(tmp_path):
    browser = find_browser()
    if browser is None:
        pytest.skip("на машине нет Chrome или Edge — скачивать негде")
    options = {**context_options(browser, sending=True, as_person=False), "headless": True}
    async with async_playwright() as playwright:
        context = await playwright.chromium.launch_persistent_context(str(tmp_path / "profile"), **options)
        page = await context.new_page()
        await page.set_content('<a href="data:application/pdf;base64,JVBERi0=" download="cv.pdf">cv</a>')
        async with page.expect_download() as caught:
            await page.click("a")
        download = await caught.value
        failure = await download.failure()
        await context.close()

    assert failure is not None
