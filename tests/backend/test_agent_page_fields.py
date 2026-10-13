"""Поле страницы глазами браузера: вид, группа кружка, обязательность.

Скрипт исполняет сам браузер, поэтому и проверяется он в настоящем: подделка
страницы ответила бы заготовленным, и поломка скрипта прошла бы незамеченной.
"""

import time

import pytest
from playwright.async_api import async_playwright

from adapters.browser import find_browser
from backend.agent.page_fields import PageField, field_or_none, page_field

FORM = """
<input type=checkbox id=plain><label for=plain id=plain-label>Согласен</label>
<label id=wrapped><input type=checkbox> Рассылка</label>
<div role=checkbox id=fancy aria-checked=false><span id=fancy-inner>✓</span></div>
<div role=radiogroup><div role=radio id=r1>Да</div><div role=radio id=r2>Нет</div></div>
<div role=radiogroup><div role=radio id=s1>Да</div></div>
<fieldset id=move><input type=radio name=move id=m1 required><label for=m1 id=m1-label>Да</label>
  <input type=radio name=move id=m2></fieldset>
<div role=group aria-required=true id=any><input type=checkbox id=any1><input type=checkbox id=any2></div>
<input id=name required><div role=textbox aria-required=true id=custom></div><input id=nick>
<button id=send>Отправить</button>
"""


@pytest.fixture
async def page():
    browser = find_browser()
    if browser is None:
        pytest.skip("на машине нет Chrome или Edge — скрипт исполнять негде")
    async with async_playwright() as playwright:
        launched = await playwright.chromium.launch(
            channel=browser.channel, executable_path=str(browser.executable) if browser.executable else None)
        one = await launched.new_page()
        await one.set_content(FORM)
        yield one
        await launched.close()


@pytest.mark.parametrize("selector", ["#plain", "#plain-label", "#wrapped", "#fancy", "#fancy-inner"])
async def test_a_check_is_known_by_itself_its_label_and_whatever_is_inside_it(page, selector):
    assert (await page_field(page, selector)).kind == "check"


async def test_radios_of_one_group_share_it_and_two_groups_differ(page):
    r1, r2, s1 = [await page_field(page, one) for one in ("#r1", "#r2", "#s1")]
    assert r1.kind == r2.kind == "radio" and r1.group == r2.group != s1.group != ""


async def test_a_native_radio_group_is_one_by_name_from_an_option_its_label_or_the_box(page):
    groups = {(await page_field(page, one)).group for one in ("#m1", "#m1-label", "#m2", "#move")}
    assert groups == {"move"}


async def test_required_is_read_from_the_field_or_its_radio_group(page):
    assert (await page_field(page, "#name")).required
    assert (await page_field(page, "#custom")).required
    assert (await page_field(page, "#m2")).required
    assert not (await page_field(page, "#nick")).required


async def test_a_required_group_of_checks_does_not_make_every_check_required(page):
    """«Отметьте хотя бы одно»: обязательна группа, а не каждая галочка в ней."""
    assert not (await page_field(page, "#any1")).required


async def test_a_button_is_not_a_field(page):
    assert await page_field(page, "#send") == PageField("", "", False)


async def test_a_field_gone_from_the_page_answers_nothing_at_once(page):
    started = time.monotonic()
    assert await field_or_none(page, "#gone") is None
    assert time.monotonic() - started < 1
