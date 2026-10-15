"""Сканирование резюме: агент перечисляет резюме сайта, список в базе приводится к увиденному."""

from backend.agent.jobs import Source
from backend.flows.aggregator_scan import scan
from backend.models import Aggregator
from tests.dbio import only_row, put, resume_marks
from tests.factories_aggregators import aggregator_resume_row, aggregator_row
from tests.fakes.agent import finish_step, login_step, resumes_step, scripted_kit


async def test_the_reported_resumes_reach_the_base(make_pipeline, session_factory):
    site = aggregator_row(is_logged_in=True)
    await put(session_factory, site)
    kit = scripted_kit(await make_pipeline(), [resumes_step(
        [("Повар", "https://hh.ru/r/2"), ("Дизайнер", "https://hh.ru/r/1")],
    )])

    assert await scan(kit, Source.of(site)) == "ok"

    assert await resume_marks(session_factory, site.id) == [("Повар", False), ("Дизайнер", False)]


async def _can_add_after(make_pipeline, session_factory, resumes: list[tuple], many_resumes: bool) -> bool:
    site = aggregator_row(is_logged_in=True, can_add_resume=not many_resumes)
    await put(session_factory, site)
    kit = scripted_kit(await make_pipeline(), [resumes_step(resumes, many_resumes=many_resumes)])
    await scan(kit, Source.of(site))
    return (await only_row(session_factory, Aggregator)).can_add_resume


async def test_the_agents_yes_means_more_can_be_added(make_pipeline, session_factory):
    """Флаг ставит агент по признакам сайта — и тогда, когда ссылка черновика
    совпала бы с адресом, по которому заводят новое."""
    resumes = [("Повар", "https://example.test/me"), ("Повар (черновик)", "https://example.test/cv/edit")]
    assert await _can_add_after(make_pipeline, session_factory, resumes, True) is True


async def test_the_agents_no_means_no_more_resumes(make_pipeline, session_factory):
    """Агент сказал «нельзя» — «нельзя», сколько бы резюме он ни назвал."""
    resumes = [("Повар", "https://example.test/me"), ("Кондитер", "https://example.test/two")]
    assert await _can_add_after(make_pipeline, session_factory, resumes, False) is False


async def test_the_log_names_the_flag_and_the_signs_found(make_pipeline, session_factory, caplog):
    site = aggregator_row(is_logged_in=True)
    await put(session_factory, site)
    kit = scripted_kit(await make_pipeline(), [resumes_step(
        [("Повар", "https://hh.ru/r/1")], signs_found="страница «Мои резюме»")])

    with caplog.at_level("INFO"):
        await scan(kit, Source.of(site))

    assert "можно ещё одно — да" in caplog.text and "страница «Мои резюме»" in caplog.text


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
    assert await resume_marks(session_factory, site.id) == [("Было", False)]
