"""Обход источника: искатель находит, и каждая находка проходит весь цикл до
отклика, прежде чем он ищет дальше; last_run_at двигается только по done."""

import asyncio

import pytest

from backend.agent.jobs import Source
from backend.agent.sessions import SESSION_LIMIT_SEC
from backend.agent.stops import HumanTimeout, LimitExhausted, ResumeMissing
from backend.flows.aggregator_round import seek_source
from backend.models import Aggregator, ProfileLanguage, Vacancy
from tests.backend.fixtures.applying import PAGE
from tests.backend.fixtures.flows import similar_by_hand
from tests.dbio import all_rows, put
from tests.factories import blacklist_row, profile_row
from tests.factories_aggregators import aggregator_row
from tests.fakes.agent import LimitHit, captcha_step, finish_step, scripted_kit, submit_step

pytestmark = pytest.mark.usefixtures("one_vector")


@pytest.fixture
def seek(make_pipeline, session_factory):
    """Обход одного источника по сценарию; ответ — переданное откликателю одним
    перечнем (пусто — ничего), строка источника и набор."""

    async def run(steps, human_limit=3600.0, on_kit=None, **source):
        row = aggregator_row(**{"host": "site.test", **source})
        await put(session_factory, row)
        kit = scripted_kit(await make_pipeline(), steps, human_limit=human_limit)
        if on_kit is not None:
            await on_kit(kit)
        await seek_source(kit, Source.of(row))
        stored = [a for a in await all_rows(session_factory, Aggregator) if a.id == row.id][0]
        handed = [vacancy_id for ids in kit.pipeline.applied for vacancy_id in ids]
        return handed, stored, kit

    return run


async def _submit(tools, url=PAGE):
    await tools["submit_vacancy"](text=f"Текст {url}", url=url, published="", contacts=[])


_submit_and_finish = submit_step(PAGE)


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


async def test_each_find_is_handed_over_before_the_next_one(seek, parsed, monkeypatch):
    """Три находки — три передачи по одной, каждая сразу после своего разбора."""
    parsed_when_applied = []

    async def step(tools):
        for number in (1, 2, 3):
            await _submit(tools, url=f"https://site.test/vacancy/{number}")
        await tools["finish"](result="done")

    async def watch(kit):
        similar_by_hand(kit.pipeline, monkeypatch)

        async def apply(ids):
            parsed_when_applied.append(len(parsed))
            kit.pipeline.applied.append(list(ids))
        kit.pipeline.apply = apply

    handed, _, kit = await seek([step], on_kit=watch)

    assert [len(ids) for ids in kit.pipeline.applied] == [1, 1, 1] and len(handed) == 3
    assert parsed_when_applied == [1, 2, 3]


async def test_a_crash_mid_session_keeps_what_already_went_through(seek, session_factory, parsed):
    """Найденное до сбоя уже прошло свой цикл; сбой кончает обход источника, не оборот."""
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


@pytest.mark.parametrize("stopper", [LimitExhausted, HumanTimeout], ids=["лимит", "срок человека"])
async def test_a_stopper_inside_a_find_stops_the_round_after_the_session(seek, parsed, stopper):
    """Беда, снимающая работу, посреди вложенного отклика: агенту — «заверши»,
    а сама беда поднимается, когда сессия искателя кончилась."""
    answers = []

    async def step(tools):
        answers.append(await tools["submit_vacancy"](text="Текст", url=PAGE, published="", contacts=[]))

    async def watch(kit):
        async def apply(ids):
            raise stopper
        kit.pipeline.apply = apply

    with pytest.raises(stopper):
        await seek([step], on_kit=watch)

    assert answers[0].startswith("Работа остановлена")


async def test_a_stopper_inside_a_find_outlives_a_crash_of_the_session(seek, parsed):
    """Сессия упала уже после беды, снявшей работу: поднимается беда, а не
    сбой источника — иначе обход пошёл бы к следующему источнику."""
    async def step(tools):
        await _submit(tools)
        raise RuntimeError("сломалось")

    async def watch(kit):
        async def apply(ids):
            raise ResumeMissing("site.test")
        kit.pipeline.apply = apply

    with pytest.raises(ResumeMissing):
        await seek([step], on_kit=watch)


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
async def test_the_seekers_clock_stands_while_a_person_is_awaited(seek, parsed, short_clock, host):
    """Срок искателя меряет только его работу: человек, отвечающий дольше всего
    срока, сессию не гасит, и искатель кончает её сам."""
    gates = []

    async def step(tools):
        asyncio.get_running_loop().call_later(0.2, gates[0].resolve)
        await tools["need_human"](kind="captcha")
        await tools["finish"](result="done")

    async def watch(kit):
        gates.append(kit.gate)

    _, stored, _ = await seek([step], on_kit=watch, host=host)

    assert stored.last_run_at is not None


async def test_a_seekers_tool_call_outlasts_the_whole_session(seek, parsed):
    """В вызове инструмента искателя идёт весь цикл находки до отклика: процесс
    агента не обрывает его раньше, чем кончился бы срок всей сессии."""
    _, _, kit = await seek([finish_step()])

    (plan,) = kit.run_session.plans
    assert plan.tool_timeout_ms >= SESSION_LIMIT_SEC * 1000


async def test_the_seekers_clock_stands_while_its_find_goes_through(seek, parsed, short_clock):
    """Вложенный цикл находки — разбор, отклик — в срок искателя не идёт:
    отклик дольше всего срока доходит до конца, и обход кончается сам."""
    async def watch(kit):
        async def apply(ids):
            await asyncio.sleep(0.2)
            kit.pipeline.applied.append(list(ids))
        kit.pipeline.apply = apply

    found, stored, _ = await seek([_submit_and_finish], on_kit=watch)

    assert len(found) == 1 and stored.last_run_at is not None


async def test_the_web_seeker_is_told_to_keep_off_telegram(seek, parsed):
    _, _, kit = await seek([finish_step()], name="Поиск по сети", host=None)

    (plan,) = kit.run_session.plans
    (avoided,) = [line for line in plan.task.splitlines() if "обходить стороной" in line]
    (barred,) = [line for line in plan.task.splitlines() if "чёрном списке" in line]
    hosts = ("t.me", "telegram.me", "telegra.ph")
    assert all(host in avoided for host in hosts) and not any(host in barred for host in hosts)


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


async def test_the_seeker_is_told_the_languages_to_search_in(seek, session_factory, parsed):
    """На каких языках искать, решает приложение по анкете, а не агент."""
    person = profile_row()
    await put(session_factory, person)
    await put(session_factory, ProfileLanguage(profile_id=person.id, language="Deutsch", level="A2"))
    await put(session_factory, ProfileLanguage(profile_id=person.id, language="Español", level="B1"))

    _, _, kit = await seek([finish_step()])

    (plan,) = kit.run_session.plans
    assert "Языки запросов: Español" in plan.task


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
