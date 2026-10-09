"""Инструменты браузера для агента: открыть, снять, нажать, ввести, выбрать, приложить резюме."""

import logging
from collections.abc import Awaitable, Callable
from pathlib import Path

from backend.agent.kit import AgentKit

logger = logging.getLogger(__name__)

_WAIT_MS = 15_000
_SNAPSHOT_LIMIT = 60_000
_CUT_MARK = "\n… снимок обрезан: страница длиннее, чем помещается в ответ."


def browser_tools(kit: AgentKit, resume: Path | None) -> list[Callable]:
    """Инструменты над вкладкой агента. Ответ действия — «готово; адрес: …» или «не вышло: …»."""

    async def browser_open(url: str) -> str:
        """Открыть адрес во вкладке."""
        return await _act(kit, lambda page: page.goto(url))

    async def browser_snapshot() -> str:
        """Что сейчас на странице: адрес, заголовок и дерево доступности с адресами ссылок."""
        return await _snapshot(kit)

    async def browser_click(selector: str) -> str:
        """Нажать на элемент по селектору Playwright."""
        return await _act(kit, lambda page: page.click(selector, timeout=_WAIT_MS))

    async def browser_type(selector: str, text: str) -> str:
        """Ввести текст в поле, заменив прежний."""
        return await _act(kit, lambda page: page.fill(selector, text, timeout=_WAIT_MS))

    async def browser_select(selector: str, value: str) -> str:
        """Выбрать значение в выпадающем списке."""
        return await _act(kit, lambda page: page.select_option(selector, value, timeout=_WAIT_MS))

    async def browser_attach_resume(selector: str) -> str:
        """Приложить резюме: селектор — кнопка или поле загрузки, видимые в снимке."""
        if resume is None:
            return "нет файла резюме"
        return await _act(kit, lambda page: _attach(page, selector, resume))

    async def browser_back() -> str:
        """Вернуться на предыдущую страницу."""
        return await _act(kit, lambda page: page.go_back())

    return [browser_open, browser_snapshot, browser_click, browser_type,
            browser_select, browser_attach_resume, browser_back]


async def _act(kit: AgentKit, action: Callable[..., Awaitable]) -> str:
    """Действие над страницей. Отказ Playwright — исход для агента, а не беда приложения:
    агент получает текст и решает сам."""
    from playwright.async_api import Error as PlaywrightError

    page = await kit.browser.page()
    try:
        await action(page)
    except PlaywrightError as error:
        logger.info("действие агента в браузере не вышло: %s", _first_line(error))
        return f"не вышло: {_first_line(error)}"
    return f"готово; адрес: {page.url}"


async def _snapshot(kit: AgentKit) -> str:
    from playwright.async_api import Error as PlaywrightError

    page = await kit.browser.page()
    try:
        tree = await page.locator("body").aria_snapshot(timeout=_WAIT_MS)
        title = await page.title()
    except PlaywrightError as error:
        logger.info("снимок страницы не снят: %s", _first_line(error))
        return f"не вышло: {_first_line(error)}"
    seen = f"Адрес: {page.url}\nЗаголовок: {title}\n{tree}"
    return seen if len(seen) <= _SNAPSHOT_LIMIT else seen[:_SNAPSHOT_LIMIT] + _CUT_MARK


async def _attach(page, selector: str, resume: Path) -> None:
    """Поле файла обычно скрыто: нажимается названное и ловится окно выбора файла.
    Окно не открылось — путь кладётся в само поле, если селектор указывает на него."""
    from playwright.async_api import Error as PlaywrightError

    try:
        async with page.expect_file_chooser(timeout=_WAIT_MS) as chooser_info:
            await page.click(selector, timeout=_WAIT_MS)
        chooser = await chooser_info.value
        await chooser.set_files(str(resume))
    except PlaywrightError:
        await page.set_input_files(selector, str(resume), timeout=_WAIT_MS)


def _first_line(error: Exception) -> str:
    return str(error).strip().splitlines()[0] if str(error).strip() else type(error).__name__
