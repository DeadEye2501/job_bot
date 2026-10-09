"""Инструменты браузера: что агент видит и что доходит до страницы."""

from backend.agent.tools_browser import browser_tools
from tests.fakes.agent import kit_for, tool
from tests.fakes.browser import FakeBrowser, FakePage

VACANCY = "https://site.test/vacancy/1"


def _tools(page, resume=None):
    return browser_tools(kit_for(None, browser=FakeBrowser(page)), resume)


async def test_an_opened_page_is_seen_with_its_address_and_title():
    page = FakePage(pages={VACANCY: ("Вакансия", '- heading "Python-разработчик"')})
    tools = _tools(page)

    assert await tool(tools, "browser_open")(url=VACANCY) == f"готово; адрес: {VACANCY}"
    seen = await tool(tools, "browser_snapshot")()

    assert seen.splitlines()[:2] == [f"Адрес: {VACANCY}", "Заголовок: Вакансия"]
    assert '- heading "Python-разработчик"' in seen


async def test_actions_reach_the_page():
    page = FakePage()
    tools = _tools(page)

    await tool(tools, "browser_click")(selector="text=Откликнуться")
    await tool(tools, "browser_type")(selector="#name", text="Иван")
    await tool(tools, "browser_select")(selector="#city", value="Москва")
    await tool(tools, "browser_back")()

    assert page.calls == [
        ("click", "text=Откликнуться"), ("fill", "#name", "Иван"),
        ("select", "#city", "Москва"), ("back",),
    ]


async def test_a_browser_error_reaches_the_agent_as_text():
    """Агент решает сам, что делать с отказом, — исключение оборвало бы его сессию."""
    page = FakePage(failures={"#gone": "Timeout 15000ms exceeded.\n=== logs ===\nwaiting for #gone"})

    answer = await tool(_tools(page), "browser_click")(selector="#gone")

    assert answer == "не вышло: Timeout 15000ms exceeded."


async def test_the_resume_goes_from_its_own_file(tmp_path):
    resume = tmp_path / "cv.pdf"
    page = FakePage(choosers={"text=Загрузить резюме"})

    answer = await tool(_tools(page, resume), "browser_attach_resume")(selector="text=Загрузить резюме")

    assert answer.startswith("готово")
    assert ("chooser", str(resume)) in page.calls


async def test_a_file_field_without_a_chooser_takes_the_resume_directly(tmp_path):
    """Поле файла бывает скрытым: нажатие окна не открывает, путь кладётся в само поле."""
    resume = tmp_path / "cv.pdf"
    page = FakePage()

    await tool(_tools(page, resume), "browser_attach_resume")(selector="input[type=file]")

    assert page.calls[-1] == ("input_files", "input[type=file]", str(resume))


async def test_without_a_resume_there_is_nothing_to_attach():
    page = FakePage(choosers={"text=Загрузить резюме"})

    answer = await tool(_tools(page), "browser_attach_resume")(selector="text=Загрузить резюме")

    assert answer == "нет файла резюме"
    assert page.calls == []


async def test_a_long_snapshot_is_cut_with_a_mark():
    page = FakePage(pages={VACANCY: ("Вакансия", "- text: " + "я" * 70_000)})
    tools = _tools(page)
    await tool(tools, "browser_open")(url=VACANCY)

    seen = await tool(tools, "browser_snapshot")()

    assert len(seen) < 61_000
    assert "обрезан" in seen.splitlines()[-1]
