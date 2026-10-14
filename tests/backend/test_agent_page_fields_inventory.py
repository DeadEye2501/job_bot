"""Опись полей страницы: всё, что форма просит заполнить, с подписью, видом и вариантами.

Скрипт исполняет сам браузер, поэтому и проверяется он в настоящем, как
`page_field` (`test_agent_page_fields.py`).
"""

import pytest

from backend.agent.page_fields import page_inventory
from tests.backend.fixtures.real_page import page_with

FORM = """
<label for=city>Город</label><input id=city required>
<textarea aria-label="О себе"></textarea>
<select id=grade><option value="">—</option><option>Junior</option><option>Middle</option></select>
<fieldset><legend>Формат работы</legend>
  <input type=radio name=format id=f1><label for=f1>Офис</label>
  <input type=radio name=format id=f2><label for=f2>Удалённо</label></fieldset>
<input name=phone aria-required=true placeholder="Телефон">
<label><input type=checkbox name=consent> Согласен на обработку данных</label>
<input type=hidden name=token value=x>
<input id=gone style="display:none" aria-label="Спрятано">
<button>Сохранить</button><input type=submit value="Отправить">
"""


@pytest.fixture
async def page():
    async with page_with(FORM) as one:
        yield one


async def test_every_visible_field_is_listed_with_its_label_kind_and_need(page):
    found = {entry.label: (entry.kind, entry.required) for entry in await page_inventory(page)}

    assert found == {
        "Город": ("text", True),
        "О себе": ("textarea", False),
        "": ("select", False),
        "Формат работы": ("radio", False),
        "Телефон": ("text", True),
        "Согласен на обработку данных": ("check", False),
    }


async def test_a_list_and_a_radio_group_carry_their_options(page):
    options = {entry.kind: entry.options for entry in await page_inventory(page)}

    assert options["select"] == ["Junior", "Middle"]
    assert options["radio"] == ["Офис", "Удалённо"]


async def test_the_selector_of_an_entry_finds_that_very_field(page):
    about = next(entry for entry in await page_inventory(page) if entry.label == "О себе")

    await page.locator(about.selector).fill("Текст", timeout=2000)

    assert await page.eval_on_selector("textarea", "el => el.value") == "Текст"


MESSY = """
<label>Город <select name=city><option>Москва</option><option>Казань</option></select></label>
<div role=checkbox aria-checked=false>Готов к переезду</div>
<fieldset><legend>Анкета</legend>
  <input type=radio name=trips><label>Да</label>
  <input type=radio name=shifts><label>Нет</label></fieldset>
<input type=radio aria-label="Один"><input type=radio aria-label="Другой">
<div role=combobox aria-label="Навыки"><input aria-label="Ввод навыка"></div>
<select aria-label="Грейд"><option disabled selected>Выберите</option><option>Senior</option></select>
"""


async def test_labels_are_read_without_the_field_text_and_from_the_role_element_itself():
    async with page_with(MESSY) as page:
        labels = [entry.label for entry in await page_inventory(page)]

    assert labels[:2] == ["Город", "Готов к переезду"]


async def test_groups_are_told_apart_by_name_and_lone_radios_stand_alone():
    async with page_with(MESSY) as page:
        radios = [entry for entry in await page_inventory(page) if entry.kind == "radio"]

    assert len(radios) == 4
    assert len({entry.selector for entry in radios}) == 4


async def test_a_field_wrapped_in_a_role_element_is_listed_once():
    async with page_with(MESSY) as page:
        labels = [entry.label for entry in await page_inventory(page)]

    assert "Навыки" in labels and "Ввод навыка" not in labels


async def test_a_placeholder_option_is_not_an_option():
    async with page_with(MESSY) as page:
        grade = next(entry for entry in await page_inventory(page) if entry.label == "Грейд")

    assert grade.options == ["Senior"]


async def test_a_second_inventory_never_gives_two_fields_one_selector():
    async with page_with(MESSY) as page:
        await page_inventory(page)
        await page.evaluate("""() => document.body.insertAdjacentHTML('afterbegin',
            '<input type=radio aria-label=Новый><input type=radio aria-label=Ещё>')""")
        entries = await page_inventory(page)
        counts = [await page.locator(entry.selector).count() for entry in entries]

    assert counts == [1] * len(entries)


STYLED = """
<input type=checkbox id=remote style="display:none"><label for=remote>Удалённая работа</label>
<input name=email aria-label="Почта"><dialog open><input name=email required aria-label="Вход"></dialog>
<input aria-label="Недоступно" disabled>
"""


async def test_a_native_check_hidden_behind_its_drawn_label_is_still_listed():
    async with page_with(STYLED) as page:
        labels = [entry.label for entry in await page_inventory(page)]

    assert "Удалённая работа" in labels


async def test_a_field_is_not_required_because_another_one_shares_its_name():
    async with page_with(STYLED) as page:
        mail = next(entry for entry in await page_inventory(page) if entry.label == "Почта")

    assert mail.required is False


async def test_a_disabled_field_is_not_listed():
    async with page_with(STYLED) as page:
        labels = [entry.label for entry in await page_inventory(page)]

    assert "Недоступно" not in labels
