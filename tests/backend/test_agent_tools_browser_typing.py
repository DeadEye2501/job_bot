"""Ввод в редактор форматированного текста: набор с клавиатуры, а не прямое заполнение.

Редактор держит текст в своей модели и обновляет её по событиям клавиатуры;
прямое заполнение блока он не видит, и при сохранении остаётся старый текст.
Проверяется настоящим браузером: подделка страницы не знает, какие события
браузер шлёт при заполнении, а какие при наборе.
"""

from backend.agent.tools_browser import browser_tools
from tests.backend.fixtures.real_page import page_with
from tests.fakes.agent import kit_for, tool
from tests.fakes.browser import FakeBrowser

EDITOR = """
<div id=about contenteditable=true>старый текст</div>
<script>
  window.typed = "";
  document.getElementById("about").addEventListener("keydown", (e) => {
    if (e.key.length === 1 && !e.ctrlKey) window.typed += e.key;
  });
</script>
"""


async def test_a_rich_text_editor_gets_the_text_typed_key_by_key():
    async with page_with(EDITOR) as page:
        tools = browser_tools(kit_for(None, browser=FakeBrowser(page)), None, None)

        answer = await tool(tools, "browser_type")(selector="#about", text="Backend developer")

        assert answer.startswith("готово")
        assert await page.evaluate("window.typed") == "Backend developer"
        assert await page.inner_text("#about") == "Backend developer"


async def test_what_the_agent_types_is_written_to_the_log(caplog):
    """По журналу видно, что агент вписал и в какое поле: за быстрым агентом
    глазами не уследить."""
    async with page_with("<input id=link>") as page:
        tools = browser_tools(kit_for(None, browser=FakeBrowser(page)), None, None)

        with caplog.at_level("INFO", logger="backend.agent.tools_browser"):
            await tool(tools, "browser_type")(selector="#link", text="https://example.com/x")

    (line,) = [r.getMessage() for r in caplog.records if r.getMessage().startswith("ввод агента")]
    assert "#link" in line and "'https://example.com/x'" in line and "готово" in line
