"""Раскладка страницы при заполнении резюме: что принимается сразу, что идёт к
проверяющему и сколько раз."""

import pytest

from backend.agent import tools_fill
from backend.agent.jobs import Finished
from backend.agent.tools_fill import fill_tools
from backend.llm.fill_review import Verdict
from backend.payloads import FieldEntry
from tests.fakes.agent import fill_job, kit_for, layout_item, tool
from tests.fakes.browser import FakeBrowser, FakePage

FORM = "https://hh.ru/resume/edit"
INVENTORY = [FieldEntry("#about", "О себе", "textarea", False, []),
             FieldEntry("#skills", "Навыки", "text", False, [])]


@pytest.fixture
def stand(monkeypatch, make_pipeline):
    """Страница резюме с описью `INVENTORY`; проверяющий отвечает из `verdicts`
    (по умолчанию — «убедительно») и помнит каждый вызов."""

    async def make(verdicts=None):
        page = FakePage()
        page.url = FORM
        job = fill_job()
        calls = []

        async def review(_lm, _model, inventory, items):
            calls.append([item["selector"] for item in items])
            return {item["selector"]: (verdicts or {}).get(item["selector"], Verdict(True, "", None))
                    for item in items}

        async def inventory_of(_page):
            return INVENTORY

        monkeypatch.setattr(tools_fill, "review_fallbacks", review)
        monkeypatch.setattr(tools_fill, "page_inventory", inventory_of)
        tools = fill_tools(kit_for(await make_pipeline(), browser=FakeBrowser(page)), job)
        return page, job, tools, calls

    return make


async def test_an_item_for_its_own_field_is_accepted_without_the_reviewer(stand):
    _, job, tools, calls = await stand()

    await tool(tools, "submit_layout")(items=[layout_item("#skills", "Вышивка, раскрой")])

    assert job.accepted[(FORM, "#skills")]["value"] == "Вышивка, раскрой" and calls == []


async def test_a_convincing_fallback_is_accepted_and_an_unconvincing_one_comes_back(stand):
    _, job, tools, _ = await stand({"#notes": Verdict(False, "есть поле «Навыки»", "#skills")})

    answer = await tool(tools, "submit_layout")(items=[
        layout_item("#about", "Район: Заречный", "поля района нет"),
        layout_item("#notes", "Навыки: вышивка", "поля навыков нет"),
    ])

    assert (FORM, "#about") in job.accepted and (FORM, "#notes") not in job.accepted
    assert "есть поле «Навыки»" in answer and "#skills" in answer


async def test_two_items_for_one_field_are_refused_together(stand):
    """Вписывается поле целиком: два пункта в одно поле — одно из них потерялось бы."""
    _, job, tools, _ = await stand()

    answer = await tool(tools, "submit_layout")(items=[
        layout_item("#about", "Район: Заречный", "поля района нет"),
        layout_item("#about", "Навыки: вышивка", "поля навыков нет"),
    ])

    assert (FORM, "#about") not in job.accepted and "одно поле" in answer


async def test_a_refused_fallback_sent_again_without_a_reason_is_not_accepted(stand):
    """Поле, однажды названное общим, остаётся общим: без обоснования в него не вписать."""
    _, job, tools, calls = await stand({"#about": Verdict(False, "есть поле", "#skills")})

    await tool(tools, "submit_layout")(items=[layout_item("#about", "Навыки: вышивка", "нет поля")])
    await tool(tools, "submit_layout")(items=[layout_item("#about", "Навыки: вышивка")])

    assert (FORM, "#about") not in job.accepted and len(calls) == 1


async def test_a_page_gets_two_reviews_and_the_third_fallback_is_not_accepted(stand, caplog):
    _, job, tools, calls = await stand({"#about": Verdict(False, "есть поле", None)})
    fallback = layout_item("#about", "Навыки: вышивка", "поля навыков нет")

    for _ in range(2):
        await tool(tools, "submit_layout")(items=[fallback])
    caplog.clear()
    answer = await tool(tools, "submit_layout")(items=[{**fallback, "fallback_reason": "иначе"}])

    assert len(calls) == 2 and (FORM, "#about") not in job.accepted
    assert "проверок больше нет" in answer
    assert any("не пропустил" in record.getMessage() for record in caplog.records)


async def test_another_page_has_its_own_two_reviews(stand):
    page, _, tools, calls = await stand({"#about": Verdict(False, "есть поле", None)})
    fallback = layout_item("#about", "Навыки: вышивка", "поля навыков нет")

    for _ in range(2):
        await tool(tools, "submit_layout")(items=[fallback])
    page.url = "https://hh.ru/resume/edit/step2"
    await tool(tools, "submit_layout")(items=[fallback])

    assert len(calls) == 3


async def test_missing_required_data_ends_the_fill_with_the_fields_named(stand):
    _, job, tools, _ = await stand()

    await tool(tools, "report_required_missing")(labels=["Гражданство", "Дата рождения"])

    assert job.outcome == Finished("required_missing", "Гражданство, Дата рождения")


async def test_a_fallback_already_accepted_is_not_reviewed_again(stand):
    """Новые поля на той же странице — новая раскладка; принятое в ней не тратит проверок."""
    _, job, tools, calls = await stand()
    fallback = layout_item("#about", "Навыки: вышивка", "поля навыков нет")

    for _ in range(3):
        await tool(tools, "submit_layout")(items=[fallback, layout_item("#skills", "Вышивка")])

    assert len(calls) == 1 and (FORM, "#about") in job.accepted


async def test_a_field_filled_in_an_earlier_layout_is_not_called_skipped(stand):
    _, job, tools, _ = await stand()

    await tool(tools, "submit_layout")(items=[layout_item("#skills", "Вышивка")])
    await tool(tools, "submit_layout")(items=[layout_item("#about", "Шью на заказ")])

    assert job.skipped[FORM] == []
