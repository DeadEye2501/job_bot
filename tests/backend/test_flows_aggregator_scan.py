"""Сканирование резюме: агент перечисляет резюме сайта, список в базе приводится к увиденному."""

from backend.agent.jobs import Source
from backend.flows.aggregator_scan import scan
from backend.models import Aggregator
from backend.repository.aggregator_resumes import resumes_of
from tests.dbio import only_row, put
from tests.factories_aggregators import aggregator_resume_row, aggregator_row
from tests.fakes.agent import finish_step, login_step, resumes_step, scripted_kit


async def _titles(session_factory, aggregator_id: int) -> list[str]:
    async with session_factory() as session:
        return [r.title for r in await resumes_of(session, aggregator_id)]


async def test_the_reported_resumes_reach_the_base(make_pipeline, session_factory):
    site = aggregator_row(is_logged_in=True)
    await put(session_factory, site)
    kit = scripted_kit(await make_pipeline(), [resumes_step(
        [("Повар", "https://hh.ru/r/2"), ("Дизайнер", "https://hh.ru/r/1")], can_add=True
    )])

    assert await scan(kit, Source.of(site)) == "ok"

    assert await _titles(session_factory, site.id) == ["Повар", "Дизайнер"]
    assert (await only_row(session_factory, Aggregator)).can_add_resume is True


async def test_the_scan_works_in_the_agent_profile_of_its_site(make_pipeline, session_factory):
    site = aggregator_row(is_logged_in=True)
    await put(session_factory, site)
    kit = scripted_kit(await make_pipeline(), [resumes_step([])])

    await scan(kit, Source.of(site))

    assert kit.browser.calls[-1] == ("profile", site.id) and kit.browser.as_person is False


async def test_a_finish_without_a_report_is_not_an_update(make_pipeline, session_factory):
    site = aggregator_row(is_logged_in=True)
    await put(session_factory, site)
    kit = scripted_kit(await make_pipeline(), [finish_step()])

    assert await scan(kit, Source.of(site)) == "error"


async def test_a_scan_that_found_no_login_says_so(make_pipeline, session_factory):
    site = aggregator_row(is_logged_in=True)
    await put(session_factory, site)
    kit = scripted_kit(await make_pipeline(), [login_step(False)])

    assert await scan(kit, Source.of(site)) == "not_logged_in"


async def test_a_session_without_a_report_leaves_the_list_alone(make_pipeline, session_factory):
    site = aggregator_row(is_logged_in=True)
    await put(session_factory, site)
    await put(session_factory, aggregator_resume_row(site.id, title="Было"))

    async def silent(tools):
        return None

    kit = scripted_kit(await make_pipeline(), [silent])

    assert await scan(kit, Source.of(site)) == "error"
    assert await _titles(session_factory, site.id) == ["Было"]
