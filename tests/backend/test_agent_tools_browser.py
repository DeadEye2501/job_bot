"""Инструменты браузера: что агент видит и что доходит до страницы."""

from backend.agent.jobs import Dropped
from backend.agent.tools_browser import browser_tools
from tests.fakes.agent import apply_job, kit_for, page_item, tool
from tests.fakes.browser import FakeBrowser, FakePage

VACANCY = "https://site.test/vacancy/1"


def _tools(page, resume=None):
    return browser_tools(kit_for(None, browser=FakeBrowser(page)), resume)


def _item(selector, value, kind="text", url=VACANCY):
    """Пункт, подтверждённый человеком на странице `url`."""
    return {(url, selector): page_item(selector, value, kind=kind)}


async def _strict(confirmed, outcome=None, fields=None):
    """Страница вакансии под подтверждением: ввод — только подтверждённого.
    `fields` — что страница называет полями: селектор → (вид, группа)."""
    page = FakePage(fields=fields)
    job = apply_job(1, confirming=True, confirmed=confirmed, outcome=outcome)
    tools = browser_tools(kit_for(None, browser=FakeBrowser(page)), None, job)
    await tool(tools, "browser_open")(url=VACANCY)
    page.calls.clear()
    return page, tools


async def test_after_finishing_nothing_reaches_the_page():
    """Человек закончил — «Отправить» не нажимается, что бы агент ни решил."""
    page, tools = await _strict(_item("#name", "Иван"), outcome=Dropped())

    await tool(tools, "browser_type")(selector="#name", text="Иван")
    answer = await tool(tools, "browser_click")(selector="text=Отправить")

    assert answer.startswith("не вышло") and page.calls == []


async def test_under_confirmation_an_unconfirmed_field_is_not_typed_into():
    page, tools = await _strict({})

    answer = await tool(tools, "browser_type")(selector="#name", text="Иван")

    assert answer.startswith("не вышло") and page.calls == []


async def test_the_confirmed_text_goes_into_the_confirmed_field():
    page, tools = await _strict(_item("#name", "Иван Петров"))

    await tool(tools, "browser_type")(selector="#name", text="Иван Петров")

    assert page.calls == [("fill", "#name", "Иван Петров")]


async def test_text_other_than_the_confirmed_is_refused():
    """Человек поправил ответ модели — модельный исходный на страницу уже не попадает."""
    page, tools = await _strict(_item("#name", "Иван Петров"))

    answer = await tool(tools, "browser_type")(selector="#name", text="Иван")

    assert "Иван Петров" in answer and page.calls == []


async def test_confirmed_text_into_another_field_is_refused():
    page, tools = await _strict(_item("#name", "Иван Петров"))

    await tool(tools, "browser_type")(selector="#phone", text="Иван Петров")

    assert page.calls == []


async def test_a_field_confirmed_on_another_page_is_not_confirmed_here():
    """Страница сменилась за время ожидания — её поля человек не видел."""
    page, tools = await _strict(_item("#name", "Иван Петров", url="https://site.test/other"))

    await tool(tools, "browser_type")(selector="#name", text="Иван Петров")

    assert page.calls == []


async def test_an_empty_confirmed_field_goes_empty():
    page, tools = await _strict(_item("#patronymic", ""))

    await tool(tools, "browser_type")(selector="#patronymic", text="")

    assert page.calls == [("fill", "#patronymic", "")]


async def test_an_unconfirmed_list_is_not_chosen_in():
    page, tools = await _strict({})

    await tool(tools, "browser_select")(selector="#city", value="Москва")

    assert page.calls == []


async def test_a_confirmed_list_takes_the_option_the_agent_chose():
    page, tools = await _strict(_item("#city", "москва", kind="choice"))

    await tool(tools, "browser_select")(selector="#city", value="Москва")

    assert page.calls == [("select", "#city", "Москва")]


async def test_a_click_on_a_confirmed_check_sets_the_confirmed_mark_every_time():
    """Нажатие не переключает галочку, а ставит подтверждённое: повтор её не снимет."""
    page, tools = await _strict(_item("#agree", "true", kind="check"))

    await tool(tools, "browser_click")(selector="#agree")
    await tool(tools, "browser_click")(selector="#agree")

    assert page.calls == [("check", "#agree", True), ("check", "#agree", True)]


async def test_a_confirmed_empty_check_stays_empty():
    page, tools = await _strict(_item("#ads", "false", kind="check"))

    await tool(tools, "browser_click")(selector="#ads")

    assert page.calls == [("check", "#ads", False)]


async def test_a_click_on_an_unconfirmed_check_is_refused():
    """Галочку, которую человек не видел, агент не ставит — ни ею самой, ни подписью к ней."""
    page, tools = await _strict({}, fields={"#ads": ("check", ""), "text=Хочу рассылку": ("check", "")})

    await tool(tools, "browser_click")(selector="#ads")
    await tool(tools, "browser_click")(selector="text=Хочу рассылку")

    assert page.calls == []


async def test_a_radio_in_a_confirmed_group_is_clicked():
    """Вариант переключателя выбирает агент, ближайший к подтверждённому, — в подтверждённой группе."""
    fields = {"#relocate": ("", "relocate"), "#relocate-yes": ("radio", "relocate")}
    page, tools = await _strict(_item("#relocate", "да", kind="choice"), fields=fields)

    await tool(tools, "browser_click")(selector="#relocate-yes")

    assert page.calls == [("click", "#relocate-yes")]


async def test_a_radio_of_an_unconfirmed_group_is_refused():
    fields = {"#relocate": ("", "relocate"), "#trips-yes": ("radio", "trips")}
    page, tools = await _strict(_item("#relocate", "да", kind="choice"), fields=fields)

    answer = await tool(tools, "browser_click")(selector="#trips-yes")

    assert answer.startswith("не вышло") and page.calls == []


async def test_clicks_off_the_fields_stay_as_they_were():
    page, tools = await _strict(_item("#agree", "true", kind="check"))

    await tool(tools, "browser_click")(selector="text=Отправить")

    assert page.calls == [("click", "text=Отправить")]


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
