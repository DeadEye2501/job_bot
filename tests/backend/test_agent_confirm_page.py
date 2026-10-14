"""Агент подтверждает страницу у человека: что вернулось, то и впишется; «Закончить»
— окончательный исход, который ни отклик, ни неудача не перепишут."""

from adapters.agent_mcp import tool_host
from backend.agent.jobs import Applied, Dropped, Failed
from backend.agent.tools_applier import applier_tools
from backend.agent.tools_common import common_tools
from backend.models import Application, Screening
from tests.dbio import all_rows, put
from tests.factories import vacancy_row
from tests.fakes.agent import apply_job, edited, finished, kit_for, page_item, tool, under_confirmation
from tests.fakes.browser import FakeBrowser, FakePage

PAGE = "https://site.test/vacancy/1/apply"


async def _applier(make_pipeline, session_factory, answer, *, confirming=True, fields=None):
    """Откликатель на странице формы; человек отвечает окну `answer`; `fields` —
    что страница говорит о своих полях (`FakePage`)."""
    vacancy = vacancy_row()
    await put(session_factory, vacancy)
    page = FakePage(fields=fields)
    page.url = PAGE
    kit, asked = await under_confirmation(kit_for(await make_pipeline(), browser=FakeBrowser(page)), answer)
    job = apply_job(vacancy.id, method="aggregator", target=PAGE, confirming=confirming)
    return job, [*common_tools(kit, job), *applier_tools(kit, job)], asked


async def test_the_window_knows_which_fields_the_page_requires(make_pipeline, session_factory):
    """Обязательность берётся у самой страницы, а не со слов агента."""
    _, tools, asked = await _applier(make_pipeline, session_factory, edited({}), fields={"#name": ("", "", True)})

    await tool(tools, "need_human")(kind="confirm", items=[page_item("#name", "Иван"), page_item("#nick", "")])

    assert [item["required"] for item in asked[0]["items"]] == [True, False]


async def test_the_letter_written_is_the_one_confirmed(make_pipeline, session_factory):
    """Человек поправил письмо — в запись ложится правленое, а не пересказ агента."""
    job, tools, _ = await _applier(make_pipeline, session_factory, edited({"": "Правленое письмо"}))
    await tool(tools, "need_human")(kind="confirm", items=[page_item("#letter", "Исходное", label="")])

    await tool(tools, "record_application")(via="aggregator", target=PAGE)

    (row,) = await all_rows(session_factory, Application)
    assert row.letter == "Правленое письмо"


async def test_the_page_is_confirmed_as_the_person_left_it(make_pipeline, session_factory):
    job, tools, _ = await _applier(make_pipeline, session_factory, edited({"Имя": "Иван Петров"}))

    answer = await tool(tools, "need_human")(kind="confirm", items=[page_item("#name", "Иван")])

    assert job.confirmed[(PAGE, "#name")]["value"] == "Иван Петров"
    assert "Иван Петров" in answer


async def test_without_confirmation_the_agent_has_nothing_to_confirm_with(make_pipeline, session_factory):
    """Режим решён один раз при постановке задачи: вне него пунктов зову человека не передать."""
    job, tools, asked = await _applier(make_pipeline, session_factory, finished, confirming=False)

    await tool_host(tools).call_tool("need_human", {"kind": "confirm", "items": [page_item("#name", "Иван")]})

    assert asked == [] and job.confirmed == {} and job.outcome is None


async def test_finishing_is_final_for_the_whole_session(make_pipeline, session_factory):
    job, tools, _ = await _applier(make_pipeline, session_factory, finished)

    await tool(tools, "need_human")(kind="confirm", items=[page_item("#name", "Иван")])
    await tool(tools, "finish")(result="platform_closed")
    await tool(tools, "report_failure")(reason="передумал")
    await tool(tools, "record_application")(via="aggregator", target=PAGE)

    assert job.outcome == Dropped()
    assert await all_rows(session_factory, Application) == []


async def test_a_send_without_fields_is_confirmed_too(make_pipeline, session_factory):
    """Отклик одной кнопкой: полей нет, а отправка необратима — окно без пунктов,
    и «Закончить» его отменяет."""
    job, tools, asked = await _applier(make_pipeline, session_factory, finished)

    await tool(tools, "need_human")(kind="confirm", items=[])

    assert asked[0]["items"] == [] and job.outcome == Dropped()


async def test_finishing_after_the_application_leaves_it_applied(make_pipeline, session_factory):
    """Отклик уже у работодателя: «Закончить» на вопросах после отправки его не отменяет."""
    job, tools, _ = await _applier(make_pipeline, session_factory, finished)
    job.outcome = Applied(7)

    await tool(tools, "need_human")(kind="confirm", items=[page_item("#extra", "Да", label="Ещё?")])

    assert job.outcome == Applied(7)


async def test_a_page_shown_again_carries_what_the_person_confirmed(make_pipeline, session_factory):
    """Сайт отверг поле — окно показывает правку человека с ошибкой сайта, а не ответ модели."""
    job, tools, asked = await _applier(make_pipeline, session_factory, edited({"Имя": "Иван Петров"}))
    need_human = tool(tools, "need_human")

    await need_human(kind="confirm", items=[page_item("#name", "Иван")])
    await need_human(kind="confirm", items=[page_item("#name", "Иван", error="Только латиница")])

    (shown,) = asked[1]["items"]
    assert (shown["value"], shown["error"]) == ("Иван Петров", "Только латиница")


async def test_the_next_step_at_the_same_address_shows_the_model_answer(make_pipeline, session_factory):
    """Шаги формы бывают на одном адресе: другое поле под тем же селектором — не прежнее."""
    job, tools, asked = await _applier(make_pipeline, session_factory, edited({"Имя": "Иван Петров"}))
    need_human = tool(tools, "need_human")

    await need_human(kind="confirm", items=[page_item("#field", "Иван")])
    await need_human(kind="confirm", items=[page_item("#field", "Пять лет", label="Опыт?")])

    assert asked[1]["items"][0]["value"] == "Пять лет"


async def test_the_screening_written_is_what_was_confirmed(make_pipeline, session_factory):
    """Записывается то, что ушло, а не пересказ агента; письмо — не вопрос."""
    job, tools, _ = await _applier(make_pipeline, session_factory, edited({"Опыт?": "Пять лет"}))
    await tool(tools, "need_human")(kind="confirm", items=[
        page_item("#years", "Четыре года", label="Опыт?"),
        page_item("#remote", "true", label="Готовы к удалёнке?", kind="check"),
        page_item("#relocate", "false", label="Готовы к переезду?", kind="check"),
        page_item("#letter", "Здравствуйте", label=""),
    ])

    await tool(tools, "record_application")(via="aggregator", target=PAGE)

    rows = await all_rows(session_factory, Screening)
    assert [(s.from_us, s.text) for s in rows] == [
        (False, "Опыт?"), (True, "Пять лет"), (False, "Готовы к удалёнке?"), (True, "да"),
        (False, "Готовы к переезду?"), (True, "нет")]


async def test_questions_after_sending_are_added_once(make_pipeline, session_factory):
    """Дописанный скрининг несёт только новое: записанное прежде второй раз не ложится."""
    job, tools, _ = await _applier(make_pipeline, session_factory, edited({}))
    need_human, record = tool(tools, "need_human"), tool(tools, "record_application")
    await need_human(kind="confirm", items=[page_item("#years", "Пять лет", label="Опыт?")])
    await record(via="aggregator", target=PAGE)

    await need_human(kind="confirm", items=[page_item("#start", "Сразу", label="Когда выйдете?")])
    await record(via="aggregator", target=PAGE)

    rows = await all_rows(session_factory, Screening)
    assert [s.text for s in rows] == ["Опыт?", "Пять лет", "Когда выйдете?", "Сразу"]


async def test_two_steps_at_one_address_both_reach_the_screening(make_pipeline, session_factory):
    """Шаги формы на одном адресе под одним селектором — два вопроса, а не один."""
    job, tools, _ = await _applier(make_pipeline, session_factory, edited({}))
    need_human = tool(tools, "need_human")
    await need_human(kind="confirm", items=[page_item("#field", "Пять лет", label="Опыт?")])
    await need_human(kind="confirm", items=[page_item("#field", "Сразу", label="Когда выйдете?")])

    await tool(tools, "record_application")(via="aggregator", target=PAGE)

    rows = await all_rows(session_factory, Screening)
    assert [s.text for s in rows] == ["Опыт?", "Пять лет", "Когда выйдете?", "Сразу"]


async def test_a_failure_before_finishing_still_counts(make_pipeline, session_factory):
    """Окончательны только отклик и «Закончить»: обычная неудача по-прежнему записывается."""
    job, tools, _ = await _applier(make_pipeline, session_factory, edited({}))

    await tool(tools, "report_failure")(reason="нужного файла нет")

    assert job.outcome == Failed("нужного файла нет")
