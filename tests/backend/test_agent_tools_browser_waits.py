"""Сколько агент ждёт элемент страницы.

Свёрнутое окно браузера агента почти не рисует, и элемент ниже первого экрана
готов к нажатию только через пару секунд. Нажатие должно его дождаться, а не
отказать. Проверяется настоящим браузером: срок ожидания держит Playwright.
"""

from backend.agent.tools_browser import browser_tools
from tests.backend.fixtures.real_page import page_with
from tests.fakes.agent import kit_for, tool
from tests.fakes.browser import FakeBrowser

_LATE_BUTTON = """<script>
setTimeout(() => document.body.innerHTML = '<button onclick="document.title=1">Сохранить</button>', 1500);
</script>"""


async def test_a_click_waits_for_an_element_that_is_ready_only_after_a_while():
    async with page_with(_LATE_BUTTON) as page:
        tools = browser_tools(kit_for(None, browser=FakeBrowser(page)), None, None)

        answer = await tool(tools, "browser_click")(selector="text=Сохранить")

        assert answer.startswith("готово") and await page.title() == "1"
