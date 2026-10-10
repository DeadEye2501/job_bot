"""Фаза 1: искатель находит, конвейер разбирает, last_run_at двигается только по done."""

import pytest

from backend.agent.jobs import Source
from backend.agent.sessions import HumanTimeout, LimitExhausted
from backend.flows.aggregator_round import RoundState, seek_source
from backend.models import Aggregator, Vacancy
from tests.backend.fixtures.parse_stub import parse_into
from tests.dbio import all_rows, put
from tests.factories import blacklist_row
from tests.factories_aggregators import aggregator_row
from tests.fakes.agent import LimitHit, captcha_step, finish_step, scripted_kit

pytestmark = pytest.mark.usefixtures("one_vector")

PAGE = "https://site.test/vacancy/1"


@pytest.fixture
def parsed(monkeypatch):
    """Номера вакансий, дошедших до разбора."""
    calls = []
    parse_into(monkeypatch, calls)
    return calls


@pytest.fixture
def seek(make_pipeline, session_factory):
    """Обход одного источника по сценарию; ответ — найденное, строка источника и набор."""

    async def run(steps, human_limit=3600.0, **source):
        row = aggregator_row(**{"host": "site.test", **source})
        await put(session_factory, row)
        kit = scripted_kit(await make_pipeline(), steps, human_limit=human_limit)
        found = await seek_source(kit, RoundState(set(), web_search_id=0), Source.of(row))
        stored = [a for a in await all_rows(session_factory, Aggregator) if a.id == row.id][0]
        return found, stored, kit

    return run


async def _submit(tools, url=PAGE):
    await tools["submit_vacancy"](text=f"Текст {url}", url=url, published="", contacts=[])


async def _submit_and_finish(tools):
    await _submit(tools)
    await tools["finish"](result="done")


async def test_a_finished_search_moves_the_last_run_and_parses_what_it_found(
    seek, session_factory, parsed
):
    found, stored, _ = await seek([_submit_and_finish])

    (vacancy,) = await all_rows(session_factory, Vacancy)
    assert found == [vacancy.id] and [vacancy_id for vacancy_id, *_ in parsed] == [vacancy.id]
    assert stored.last_run_at is not None


async def test_a_search_without_finish_keeps_the_last_run_but_gives_what_it_found(
    seek, session_factory, parsed
):
    async def step(tools):
        await _submit(tools)

    found, stored, _ = await seek([step])

    (vacancy,) = await all_rows(session_factory, Vacancy)
    assert found == [vacancy.id] and stored.last_run_at is None


async def test_a_silent_embedding_model_is_a_failure_whatever_the_agent_says(
    seek, parsed, silent_embedder
):
    found, stored, _ = await seek([_submit_and_finish])

    assert found == [] and stored.last_run_at is None


async def test_a_crash_mid_session_fails_the_source_not_the_round(seek, session_factory, parsed):
    """Найденное до сбоя разбирается: фаза откликов берёт только разобранное."""
    async def step(tools):
        await _submit(tools)
        raise RuntimeError("сломалось")

    found, stored, _ = await seek([step])

    (vacancy,) = await all_rows(session_factory, Vacancy)
    assert found == [vacancy.id] and stored.last_run_at is None
    assert [vacancy_id for vacancy_id, *_ in parsed] == [vacancy.id]


async def test_an_exhausted_subscription_stops_the_round(seek, parsed):
    async def step(tools):
        raise LimitHit

    with pytest.raises(LimitExhausted):
        await seek([step])


async def test_an_expired_wait_for_a_person_stops_the_round(seek, parsed):
    with pytest.raises(HumanTimeout):
        await seek([captcha_step()], human_limit=0.01)


async def test_the_web_seeker_searches_the_web_and_avoids_the_persons_aggregators(
    seek, session_factory, parsed
):
    await put(session_factory, aggregator_row(host="board.test"))

    step = finish_step()

    _, _, kit = await seek([step], name="Поиск по сети", host=None)

    (plan,) = kit.run_session.plans
    assert plan.web_search is True and "board.test" in plan.task


@pytest.mark.parametrize("host", ["site.test", None], ids=["агрегатор", "поиск по сети"])
async def test_the_seeker_is_told_how_to_call_a_person(seek, parsed, host):
    step = finish_step()

    _, _, kit = await seek([step], host=host)

    (plan,) = kit.run_session.plans
    # Подстрока самого правила о зове человека: слово `need_human` называет и
    # промпт роли, и по нему пропажу правила не заметить.
    assert 'need_human с kind="captcha"' in plan.system_prompt


async def test_the_web_seeker_hears_of_the_blacklisted_sites(seek, session_factory, parsed):
    await put(session_factory, blacklist_row("aggregator", "barred.test"))

    step = finish_step()

    _, _, kit = await seek([step], name="Поиск по сети", host=None)

    (plan,) = kit.run_session.plans
    assert "barred.test" in plan.task


async def test_the_web_seeker_hears_that_no_site_is_blacklisted(seek, parsed):
    step = finish_step()

    _, _, kit = await seek([step], name="Поиск по сети", host=None)

    (plan,) = kit.run_session.plans
    assert "Сайты в чёрном списке: нет" in plan.task


async def test_the_pipeline_refreshes_its_snapshots_before_the_search(
    seek, monkeypatch, make_pipeline, parsed
):
    order = []

    async def step(tools):
        order.append("search")
        await tools["finish"](result="done")

    async def reload_resources(self):
        order.append("reload")

    monkeypatch.setattr("backend.flows.pipeline.IngestionPipeline.reload_resources", reload_resources)

    await seek([step])

    assert order == ["reload", "search"]
