"""Общие инструменты агента: анкета, вход, итог, неудача."""

from backend.agent.jobs import Applied, ApplyJob, Failed, Finished, LoginJob, Source
from backend.agent.tools_common import common_tools
from backend.models import Aggregator
from tests.dbio import all_rows, put
from tests.factories import profile_row
from tests.factories_aggregators import aggregator_row
from tests.fakes.agent import kit_for, tool


async def test_the_profile_tool_gives_the_whole_profile(make_pipeline, session_factory):
    await put(session_factory, profile_row())
    site = aggregator_row()
    await put(session_factory, site)
    tools = common_tools(kit_for(await make_pipeline()), LoginJob(Source.of(site)))

    assert "Имя: Иван" in await tool(tools, "profile")()


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


async def test_a_failure_is_recorded_for_the_applier(make_pipeline):
    job = ApplyJob(vacancy_id=1, method="form", target="https://site.test/f",
                   aggregator_id=None, profile_id=1, forced=False, simulated=False,
                   letter_writer="app")

    await tool(common_tools(kit_for(await make_pipeline()), job), "report_failure")(
        reason="форма требует отчество"
    )

    assert job.outcome == Failed("форма требует отчество")


async def test_a_recorded_application_cannot_be_turned_into_a_failure(make_pipeline):
    """Иначе код пошёл бы к следующему способу и откликнулся второй раз."""
    job = ApplyJob(vacancy_id=1, method="form", target="https://site.test/f",
                   aggregator_id=None, profile_id=1, forced=False, simulated=False,
                   letter_writer="app", outcome=Applied(7))
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


async def test_the_applier_asks_for_a_human_on_the_site_of_its_method(make_pipeline):
    gate = _Gate()
    job = ApplyJob(vacancy_id=1, method="form", target="https://www.Company.test/apply",
                   aggregator_id=None, profile_id=1, forced=False, simulated=False,
                   letter_writer="app")
    need_human = tool(common_tools(kit_for(await make_pipeline(), gate=gate), job), "need_human")

    assert await need_human(kind="captcha") == "готово"
    assert await need_human(kind="password") != "готово"
    assert gate.asked == [("captcha", "company.test")]
