"""Инструменты искателя: известна ли вакансия и передача найденного в конвейер."""

from datetime import date

import pytest

from backend.agent.jobs import SeekJob, Source
from backend.agent.tools_seeker import seeker_tools
from backend.models import ContactAddedBy, TrashEvent, Vacancy, VacancyContact, VacancyEvent
from tests.dbio import all_rows, put
from tests.factories import blacklist_row, vacancy_row
from tests.factories_aggregators import aggregator_row, web_search_row
from tests.fakes.agent import kit_for, tool

pytestmark = pytest.mark.usefixtures("one_vector")

PAGE = "https://site.test/vacancy/1?from=list"


class _Queue:
    def __init__(self):
        self.items = []

    def put(self, vacancy_id, text):
        self.items.append((vacancy_id, text))


async def _seeker(make_pipeline, session_factory, *, limit=5):
    site = aggregator_row(host="site.test")
    await put(session_factory, site)
    job, queue = SeekJob(Source.of(site), limit=limit), _Queue()
    pipeline = await make_pipeline()
    return job, queue, seeker_tools(kit_for(pipeline), job, queue), site


async def test_a_find_on_the_open_web_is_marked_so_in_its_event(make_pipeline, session_factory):
    """«Поиск по сети» — способ поиска, а не место: событие говорит окну, что
    вакансия найдена в сети, и окно подписывает её своими словами."""
    web = web_search_row()
    await put(session_factory, web)
    job = SeekJob(Source.of(web), limit=5)
    tools = seeker_tools(kit_for(await make_pipeline()), job, _Queue())

    await tool(tools, "submit_vacancy")(
        text="Текст вакансии", url="https://company.test/jobs/1", published="", contacts=[]
    )

    (event,) = [one for one in await all_rows(session_factory, VacancyEvent) if one.kind == "found"]
    assert event.payload["web_search"] is True


async def test_a_find_on_an_aggregator_is_not_marked_as_the_open_web(make_pipeline, session_factory):
    job, queue, tools, site = await _seeker(make_pipeline, session_factory)

    await tool(tools, "submit_vacancy")(text="Текст вакансии", url=PAGE, published="", contacts=[])

    (event,) = [one for one in await all_rows(session_factory, VacancyEvent) if one.kind == "found"]
    assert event.payload["web_search"] is False


async def test_a_known_number_is_known_before_opening(make_pipeline, session_factory):
    job, queue, tools, site = await _seeker(make_pipeline, session_factory)
    await put(session_factory, vacancy_row(source_aggregator_id=site.id, source_key="vacancy/1"))

    assert await tool(tools, "is_known")(url=PAGE) == "известна"


async def test_an_unseen_number_is_new_and_a_foreign_page_is_not_ours(make_pipeline, session_factory):
    job, queue, tools, site = await _seeker(make_pipeline, session_factory)
    is_known = tool(tools, "is_known")

    assert await is_known(url=PAGE) == "новая"
    assert await is_known(url="https://other.test/vacancy/1") == "адрес не с этого источника"


async def test_a_page_deleted_as_junk_is_known_too(make_pipeline, session_factory):
    job, queue, tools, site = await _seeker(make_pipeline, session_factory)
    await put(session_factory, TrashEvent(source_aggregator_id=site.id, source_key="vacancy/1"))

    assert await tool(tools, "is_known")(url=PAGE) == "известна"


async def test_a_new_vacancy_is_stored_with_its_source_and_contacts(make_pipeline, session_factory):
    job, queue, tools, site = await _seeker(make_pipeline, session_factory)

    answer = await tool(tools, "submit_vacancy")(
        text="Текст вакансии", url=PAGE, published="2026-10-08", contacts=["HR@Site.test"]
    )

    (vacancy,) = await all_rows(session_factory, Vacancy)
    assert (vacancy.source_aggregator_id, vacancy.source_key, vacancy.source_url) == (
        site.id, "vacancy/1", PAGE
    )
    page, email = await all_rows(session_factory, VacancyContact)
    assert (page.value, page.added_by) == (PAGE, ContactAddedBy.AGENT)
    assert (email.match_key, email.added_by) == ("hr@site.test", ContactAddedBy.AGENT)
    assert queue.items == [(vacancy.id, "Текст вакансии")]
    assert answer.startswith("принята") and "ещё 4" in answer
    assert job.found == [vacancy.id]
    assert vacancy.posted_at.date() == date(2026, 10, 8)


async def test_the_same_page_twice_is_a_repeat_and_costs_nothing(
    make_pipeline, session_factory, one_vector
):
    """Повтор по номеру узнаётся до модели эмбеддингов: ни вызова, ни второго разбора."""
    job, queue, tools, site = await _seeker(make_pipeline, session_factory)
    submit = tool(tools, "submit_vacancy")
    await submit(text="Текст", url=PAGE, published="", contacts=[])

    answer = await submit(text="Текст", url=PAGE, published="", contacts=[])

    assert answer.startswith("повтор") and job.submitted == 1
    assert len(one_vector) == 1 and len(queue.items) == 1


async def test_a_page_of_another_site_is_refused(make_pipeline, session_factory):
    job, queue, tools, site = await _seeker(make_pipeline, session_factory)

    answer = await tool(tools, "submit_vacancy")(
        text="Текст", url="https://other.test/vacancy/1", published="", contacts=[]
    )

    assert answer.startswith("пропущена") and await all_rows(session_factory, Vacancy) == []


async def test_a_silent_embedding_model_refuses(make_pipeline, session_factory, silent_embedder):
    job, queue, tools, site = await _seeker(make_pipeline, session_factory)

    answer = await tool(tools, "submit_vacancy")(text="Текст", url=PAGE, published="", contacts=[])

    assert answer.startswith("отказ") and job.refused


async def test_the_limit_stops_new_submissions(make_pipeline, session_factory):
    job, queue, tools, site = await _seeker(make_pipeline, session_factory, limit=0)

    answer = await tool(tools, "submit_vacancy")(text="Текст", url=PAGE, published="", contacts=[])

    assert answer.startswith("предел исчерпан") and await all_rows(session_factory, Vacancy) == []


async def test_a_page_like_a_parsed_vacancy_is_a_repeat(make_pipeline, session_factory):
    """Та же вакансия с другого источника — повтор: вторую строку не заводят и в разбор не ставят."""
    known = vacancy_row(is_parsed=True, embedding=[0.1, 0.2])
    await put(session_factory, known)
    job, queue, tools, site = await _seeker(make_pipeline, session_factory)

    answer = await tool(tools, "submit_vacancy")(text="Текст", url=PAGE, published="", contacts=[])

    assert answer.startswith("повтор") and job.submitted == 0
    assert [v.id for v in await all_rows(session_factory, Vacancy)] == [known.id]
    assert queue.items == []


async def test_a_page_like_an_unparsed_vacancy_finishes_it(make_pipeline, session_factory):
    """Похожая брошена недоразобранной — её дочитывают текстом найденной страницы."""
    known = vacancy_row(is_parsed=False, embedding=[0.1, 0.2])
    await put(session_factory, known)
    job, queue, tools, site = await _seeker(make_pipeline, session_factory)

    answer = await tool(tools, "submit_vacancy")(text="Полный текст", url=PAGE, published="", contacts=[])

    assert answer.startswith("повтор")
    assert queue.items == [(known.id, "Полный текст")]


async def test_a_repost_of_a_page_found_this_session_is_not_parsed_twice(make_pipeline, session_factory):
    """Своя находка ещё ждёт разбора — тот же текст под другим номером её второй раз в очередь не ставит."""
    job, queue, tools, site = await _seeker(make_pipeline, session_factory)
    submit = tool(tools, "submit_vacancy")
    await submit(text="Текст", url=PAGE, published="", contacts=[])

    answer = await submit(text="Текст", url="https://site.test/vacancy/2", published="", contacts=[])

    assert answer.startswith("повтор")
    assert len(queue.items) == 1


async def test_each_accepted_page_moves_the_progress_in_the_window(make_pipeline, session_factory):
    site = aggregator_row(host="site.test")
    await put(session_factory, site)
    pipeline = await make_pipeline()
    steps = []
    pipeline.on_progress = lambda *step: steps.append(step)
    job = SeekJob(Source.of(site), limit=5)
    submit = tool(seeker_tools(kit_for(pipeline), job, _Queue()), "submit_vacancy")

    await submit(text="Текст", url=PAGE, published="", contacts=[])

    assert steps == [("aggregator", "Обход HeadHunter", 1, 5)]


BARRED_PAGE = "https://jobs.barred.test/vacancy/1"


async def _web_seeker(make_pipeline, session_factory):
    """Искатель «Поиска по сети», а у человека в отсеве сайт `barred.test`."""
    web = web_search_row()
    await put(session_factory, web, blacklist_row("aggregator", "barred.test"))
    job, queue = SeekJob(Source.of(web), limit=5), _Queue()
    return job, queue, seeker_tools(kit_for(await make_pipeline()), job, queue)


async def test_a_page_of_a_blacklisted_site_is_not_to_be_opened(make_pipeline, session_factory):
    _, _, tools = await _web_seeker(make_pipeline, session_factory)

    answer = await tool(tools, "is_known")(url=BARRED_PAGE)

    assert "чёрном списке" in answer and "не открывай" in answer


async def test_a_page_of_a_blacklisted_site_is_skipped_without_costing_the_limit(
    make_pipeline, session_factory
):
    """Не отказ — отказ обрывает обход; сайт в отсеве лишь пропускается."""
    job, queue, tools = await _web_seeker(make_pipeline, session_factory)

    answer = await tool(tools, "submit_vacancy")(
        text="Текст вакансии", url=BARRED_PAGE, published="", contacts=[]
    )

    assert answer.startswith("пропущена") and "чёрном списке" in answer
    assert (await all_rows(session_factory, Vacancy), job.submitted, job.refused) == ([], 0, False)
