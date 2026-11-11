"""Браузер агента не скачивает файлов: всякая загрузка обрывается самим браузером.

Проверяется настоящим браузером: запрет ставится браузеру после подключения, и
подделка подтвердила бы только то, что команда послана, а не то, что файл не
лёг на диск. Нет на машине браузера — проверка пропускается.
"""

from tests.real_browser import real_host


async def test_a_file_the_page_offers_is_not_saved():
    async with real_host() as host:
        page = await host.page()
        await page.set_content('<a href="data:application/pdf;base64,JVBERi0=" download="cv.pdf">cv</a>')
        async with page.expect_download() as caught:
            await page.click("a")
        download = await caught.value
        failure = await download.failure()

    assert failure is not None
