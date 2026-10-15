"""Сколько агент ждёт элемент, которого на странице нет.

Агент действует по свежему снимку, поэтому отсутствующий элемент — не «ещё не
появился», а «его нет»: ответ должен прийти сразу, а не через долгий срок.
Проверяется настоящим браузером: срок ожидания держит Playwright.
"""

import time

from backend.agent.tools_browser import browser_tools
from tests.backend.fixtures.real_page import page_with
from tests.fakes.agent import kit_for, tool
from tests.fakes.browser import FakeBrowser


async def test_a_click_on_a_missing_element_answers_within_a_couple_of_seconds():
    async with page_with("<button>Сохранить</button>") as page:
        tools = browser_tools(kit_for(None, browser=FakeBrowser(page)), None, None)

        started = time.monotonic()
        answer = await tool(tools, "browser_click")(selector="text=Нет такого")

        assert answer.startswith("не вышло") and time.monotonic() - started < 2
