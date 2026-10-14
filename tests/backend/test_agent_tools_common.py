"""Общие инструменты агента: анкета, вход, итог, неудача."""

from backend.agent.jobs import Applied, Failed, FillJob, Finished, LoginJob, ScanJob, Source
from backend.agent.tools_common import common_tools
from backend.models import Aggregator
from backend.payloads import SeenResume
from backend.repository.agent_profile import build_agent_profile
from tests.dbio import all_rows, put
from tests.factories import profile_row
from tests.factories_aggregators import aggregator_row
from tests.fakes.agent import TODAY, apply_job, kit_for, tool


async def test_the_profile_tool_gives_the_whole_profile(make_pipeline, session_factory):
    await put(session_factory, profile_row())
    site = aggregator_row()
    await put(session_factory, site)
    tools = common_tools(kit_for(await make_pipeline()), LoginJob(Source.of(site)))

    async with session_factory() as session:
        whole = await build_agent_profile(session, TODAY, photo=False)

    assert "Имя: Иван" in whole and await tool(tools, "profile")() == whole


async def test_a_reported_login_lands_on_its_own_aggregator(make_pipeline, session_factory):
    site = aggregator_row(is_logged_in=False)
    other = aggregator_row(host="other.test", is_logged_in=False)
    await put(session_factory, site, other)
    tools = common_tools(kit_for(await make_pipeline()), LoginJob(Source.of(site)))

    await tool(tools, "report_login")(logged_in=True)

    rows = await all_rows(session_factory, Aggregator)
    assert {a.host: a.is_logged_in for a in rows} == {"hh.ru": True, "other.test": False}


async def test_finish_records_the_outcome_of_the_session(make_pipeline, session_factory):
    site = aggregator_row()
    await put(session_factory, site)
    job = LoginJob(Source.of(site))

    await tool(common_tools(kit_for(await make_pipeline()), job), "finish")(result="done", reason="")

    assert job.outcome == Finished("done", "")


async def test_a_finish_the_role_does_not_know_is_refused(make_pipeline, session_factory):
    site = aggregator_row()
    await put(session_factory, site)
    job = LoginJob(Source.of(site))

    answer = await tool(common_tools(kit_for(await make_pipeline()), job), "finish")(
        result="vacancy_closed", reason=""
    )

    assert job.outcome is None and "не бывает" in answer


async def test_the_applier_can_finish_with_an_unfit_vacancy(make_pipeline):
    job = apply_job(1)

    await tool(common_tools(kit_for(await make_pipeline()), job), "finish")(
        result="not_fit", reason="Условие формы"
    )

    assert job.outcome == Finished("not_fit", "Условие формы")


async def test_a_failure_is_recorded_for_the_applier(make_pipeline):
    job = apply_job(1)

    await tool(common_tools(kit_for(await make_pipeline()), job), "report_failure")(
        reason="форма требует отчество"
    )

    assert job.outcome == Failed("форма требует отчество")


async def test_a_recorded_application_cannot_be_turned_into_a_failure(make_pipeline):
    """Иначе код пошёл бы к следующему способу и откликнулся второй раз."""
    job = apply_job(1, outcome=Applied(7))
    tools = common_tools(kit_for(await make_pipeline()), job)

    await tool(tools, "report_failure")(reason="передумал")
    await tool(tools, "finish")(result="platform_closed")

    assert job.outcome == Applied(7)


class _Gate:
    def __init__(self):
        self.asked = []

    async def wait(self, kind, host, _browser):
        self.asked.append((kind, host))
        return "готово"


async def test_the_login_check_cannot_call_for_a_human(make_pipeline, session_factory):
    """Проверка входа идёт после того, как человек закрыл окно: позови она его
    снова, окно открывалось бы по кругу, пока он не войдёт. Её дело — сказать
    «не вошёл» и закончить."""
    site = aggregator_row()
    await put(session_factory, site)
    tools = common_tools(kit_for(await make_pipeline()), LoginJob(Source.of(site)))

    assert "need_human" not in {one.__name__ for one in tools}
    assert "report_login" in {one.__name__ for one in tools}


async def test_the_applier_asks_for_a_human_on_the_site_of_its_method(make_pipeline):
    gate = _Gate()
    job = apply_job(1, target="https://www.Company.test/apply")
    need_human = tool(common_tools(kit_for(await make_pipeline(), gate=gate), job), "need_human")

    assert await need_human(kind="captcha") == "готово"
    assert await need_human(kind="password") != "готово"
    assert gate.asked == [("captcha", "company.test")]


async def test_the_scan_calls_a_human_on_its_site_and_marks_its_login(
    make_pipeline, session_factory
):
    """Сканирование по кнопке может упереться во вход заново и в капчу."""
    site = aggregator_row(is_logged_in=True)
    await put(session_factory, site)
    gate = _Gate()
    job = ScanJob(Source.of(site))
    tools = common_tools(kit_for(await make_pipeline(), gate=gate), job)

    assert await tool(tools, "need_human")(kind="login") == "готово"
    await tool(tools, "report_login")(logged_in=False)
    await tool(tools, "finish")(result="done")

    assert gate.asked == [("login", "hh.ru")] and job.outcome == Finished("done", "")
    assert (await all_rows(session_factory, Aggregator))[0].is_logged_in is False


async def test_a_missing_resume_is_an_outcome_only_where_a_resume_was_named(make_pipeline):
    """Без названного резюме «его не нашлось» сказать не о чем: форма работодателя
    своих резюме не держит."""
    form = apply_job(1)
    named = apply_job(1, method="aggregator", target="https://hh.ru/vacancy/1", aggregator_id=4,
                      resume=SeenResume("Повар", "https://hh.ru/resume/1"))
    kit = kit_for(await make_pipeline())

    refused = await tool(common_tools(kit, form), "finish")(result="resume_missing")
    await tool(common_tools(kit, named), "finish")(result="resume_missing")

    assert form.outcome is None and "не бывает" in refused
    assert named.outcome == Finished("resume_missing", "")


async def test_a_fill_reports_its_login_calls_a_human_and_finishes(make_pipeline, session_factory):
    """Заполнение резюме — работа на сайте: вход может слететь, капча — встретиться."""
    site = aggregator_row(is_logged_in=True)
    await put(session_factory, site)
    gate = _Gate()
    job = FillJob(Source.of(site))
    tools = common_tools(kit_for(await make_pipeline(), gate=gate), job)

    assert await tool(tools, "need_human")(kind="captcha") == "готово"
    await tool(tools, "report_login")(logged_in=False)
    await tool(tools, "finish")(result="done")

    assert gate.asked == [("captcha", "hh.ru")] and job.outcome == Finished("done", "")
    assert (await all_rows(session_factory, Aggregator))[0].is_logged_in is False


async def test_a_written_outcome_is_not_overwritten_by_a_later_finish(make_pipeline, session_factory):
    """Нехватка данных — итог заполнения; «done» следом сделало бы его успехом."""
    site = aggregator_row()
    await put(session_factory, site)
    job = FillJob(Source.of(site), outcome=Finished("required_missing", "Гражданство"))

    await tool(common_tools(kit_for(await make_pipeline()), job), "finish")(result="done")

    assert job.outcome == Finished("required_missing", "Гражданство")
