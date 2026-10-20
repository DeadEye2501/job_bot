"""Инструменты искателя: известна ли вакансия и передача найденного в конвейер."""

from datetime import date

import pytest

from backend.agent.jobs import SeekJob, Source
from backend.agent.stops import HumanTimeout, LimitExhausted
from backend.agent.tools_seeker import seeker_tools
from backend.models import ContactAddedBy, TrashEvent, Vacancy, VacancyContact, VacancyEvent
from tests.backend.fixtures.parse_stub import parse_into
from tests.dbio import all_rows, put
from tests.factories import blacklist_row, vacancy_row
from tests.factories_aggregators import aggregator_row, web_search_row
from tests.fakes.agent import kit_for, tool
from tests.fakes.browser import FakeBrowser

pytestmark = pytest.mark.usefixtures("one_vector")

PAGE = "https://site.test/vacancy/1?from=list"


async def _seeker(make_pipeline, session_factory, *, limit=5, row=None):
    """Искатель на своём источнике; ответ — задача, инструменты и набор."""
    site = row or aggregator_row(host="site.test")
    await put(session_factory, site)
    job = SeekJob(Source.of(site), limit=limit)
    kit = kit_for(await make_pipeline(), browser=FakeBrowser())
    return job, seeker_tools(kit, job), kit


async def test_a_find_on_the_open_web_is_marked_so_in_its_event(make_pipeline, session_factory, parsed):
    """«Поиск по сети» — способ поиска, а не место: событие говорит окну, что
    вакансия найдена в сети, и окно подписывает её своими словами."""
    _, tools, _ = await _seeker(make_pipeline, session_factory, row=web_search_row())

    await tool(tools, "submit_vacancy")(
        text="Текст вакансии", url="https://company.test/jobs/1", published="", contacts=[]
    )

    (event,) = [one for one in await all_rows(session_factory, VacancyEvent) if one.kind == "found"]
    assert event.payload["web_search"] is True


async def test_a_find_on_an_aggregator_is_not_marked_as_the_open_web(make_pipeline, session_factory, parsed):
    _, tools, _ = await _seeker(make_pipeline, session_factory)

    await tool(tools, "submit_vacancy")(text="Текст вакансии", url=PAGE, published="", contacts=[])

    (event,) = [one for one in await all_rows(session_factory, VacancyEvent) if one.kind == "found"]
    assert event.payload["web_search"] is False


async def test_a_known_number_is_known_before_opening(make_pipeline, session_factory):
    job, tools, _ = await _seeker(make_pipeline, session_factory)
    await put(session_factory, vacancy_row(source_aggregator_id=job.source.id, source_key="vacancy/1"))

    assert await tool(tools, "is_known")(url=PAGE) == "известна"


async def test_an_unseen_number_is_new_and_a_foreign_page_is_not_ours(make_pipeline, session_factory):
    _, tools, _ = await _seeker(make_pipeline, session_factory)
    is_known = tool(tools, "is_known")

    assert await is_known(url=PAGE) == "новая"
    assert await is_known(url="https://other.test/vacancy/1") == "адрес не с этого источника"


async def test_a_page_deleted_as_junk_is_known_too(make_pipeline, session_factory):
    job, tools, _ = await _seeker(make_pipeline, session_factory)
    await put(session_factory, TrashEvent(source_aggregator_id=job.source.id, source_key="vacancy/1"))

    assert await tool(tools, "is_known")(url=PAGE) == "известна"


async def test_a_new_vacancy_is_stored_with_its_source_and_contacts(make_pipeline, session_factory, parsed):
    job, tools, _ = await _seeker(make_pipeline, session_factory)

    answer = await tool(tools, "submit_vacancy")(
        text="Текст вакансии", url=PAGE, published="2026-10-08", contacts=["HR@Site.test"]
    )

    (vacancy,) = await all_rows(session_factory, Vacancy)
    assert (vacancy.source_aggregator_id, vacancy.source_key, vacancy.source_url) == (
        job.source.id, "vacancy/1", PAGE
    )
    page, email = await all_rows(session_factory, VacancyContact)
    assert (page.value, page.added_by) == (PAGE, ContactAddedBy.AGENT)
    assert (email.match_key, email.added_by) == ("hr@site.test", ContactAddedBy.AGENT)
    assert answer.startswith("принята") and "ещё 4" in answer
    assert vacancy.posted_at.date() == date(2026, 10, 8)


async def test_a_find_goes_the_whole_way_before_the_answer(make_pipeline, session_factory, parsed):
    """Находка разобрана и передана откликателю до ответа агенту: следующей
    вакансии он не ищет, пока по этой не прошёл весь цикл."""
    _, tools, kit = await _seeker(make_pipeline, session_factory)

    await tool(tools, "submit_vacancy")(text="Текст вакансии", url=PAGE, published="", contacts=[])

    (vacancy,) = await all_rows(session_factory, Vacancy)
    assert parsed == [(vacancy.id, "Текст вакансии", None, True)]
    assert kit.pipeline.applied == [[vacancy.id]]


async def test_after_the_cycle_the_seeker_gets_its_browser_back(make_pipeline, session_factory, parsed):
    """Отклик открывает свой профиль и уводит вкладку: искателю возвращают его
    профиль и велят вернуться к выдаче по адресу — история вкладки уже чужая."""
    job, tools, kit = await _seeker(make_pipeline, session_factory)

    async def apply(ids):
        await kit.browser.open_profile(99)
    kit.pipeline.apply = apply

    answer = await tool(tools, "submit_vacancy")(text="Текст", url=PAGE, published="", contacts=[])

    assert kit.browser.calls == [("profile", 99), ("profile", job.source.id)]
    assert "browser_open" in answer and "выдаче" in answer


async def test_after_the_cycle_the_bar_shows_the_search_again(make_pipeline, session_factory, parsed):
    """Отклик кладёт на полосу свой ход; после него полоса снова показывает поиск."""
    job, tools, kit = await _seeker(make_pipeline, session_factory)
    steps = []
    kit.pipeline.on_progress = lambda *step: steps.append(step)

    async def apply(ids):
        kit.pipeline.emit_progress("apply", "Отклик", 0, 1)
    kit.pipeline.apply = apply

    await tool(tools, "submit_vacancy")(text="Текст", url=PAGE, published="", contacts=[])

    assert steps[-1] == ("aggregator", "Обход HeadHunter", 1, 5)


async def test_a_find_not_handed_over_moves_the_bar_too(make_pipeline, session_factory, parsed):
    """Автоотклик выключен — откликателя не зовут, а полоса идёт всё равно."""
    _, tools, kit = await _seeker(make_pipeline, session_factory)
    await kit.pipeline.rs.set_app("auto_apply", "false")
    steps = []
    kit.pipeline.on_progress = lambda *step: steps.append(step)

    await tool(tools, "submit_vacancy")(text="Текст", url=PAGE, published="", contacts=[])

    assert kit.pipeline.applied == [] and steps == [("aggregator", "Обход HeadHunter", 1, 5)]


async def test_the_last_find_within_the_limit_tells_the_seeker_to_finish(
    make_pipeline, session_factory, parsed
):
    """Передана последняя по пределу — искать следующую незачем."""
    _, tools, _ = await _seeker(make_pipeline, session_factory, limit=1)

    answer = await tool(tools, "submit_vacancy")(text="Текст", url=PAGE, published="", contacts=[])

    assert answer.startswith("принята") and "предел исчерпан" in answer
    assert "browser_open" not in answer


async def test_a_broken_parse_of_one_find_does_not_stop_the_search(
    make_pipeline, session_factory, monkeypatch, caplog
):
    """Беда на одной находке — запись в журнал и поиск дальше: агент ищет
    следующую, а не кончает сессию; браузер и полоса возвращаются искателю."""

    def broken():
        raise RuntimeError("разбор упал")

    parse_into(monkeypatch, [], done=broken)
    job, tools, kit = await _seeker(make_pipeline, session_factory)
    steps = []
    kit.pipeline.on_progress = lambda *step: steps.append(step)

    answer = await tool(tools, "submit_vacancy")(text="Текст", url=PAGE, published="", contacts=[])

    assert answer.startswith("не вышло") and "browser_open" in answer
    assert job.stopper is None and kit.pipeline.applied == []
    assert kit.browser.calls == [("profile", job.source.id)]
    assert steps == [("aggregator", "Обход HeadHunter", 1, 5)]
    assert any(record.exc_info for record in caplog.records if record.name == "backend.agent.tools_seeker")


@pytest.mark.parametrize("stopper", [LimitExhausted, HumanTimeout], ids=["лимит", "срок человека"])
async def test_a_stopper_inside_the_cycle_ends_the_session(
    make_pipeline, session_factory, parsed, stopper
):
    """Лимит подписки и истёкшее ожидание внутри вложенного отклика снимают и
    поиск: агенту — «заверши», беда ждёт конца сессии, а следующая передача
    отвечает тем же, ничего не заводя."""
    job, tools, kit = await _seeker(make_pipeline, session_factory)

    async def apply(ids):
        raise stopper
    kit.pipeline.apply = apply
    submit = tool(tools, "submit_vacancy")

    first = await submit(text="Текст", url=PAGE, published="", contacts=[])
    second = await submit(text="Другой", url="https://site.test/vacancy/2", published="", contacts=[])
    known = await tool(tools, "is_known")(url="https://site.test/vacancy/3")

    assert isinstance(job.stopper, stopper)
    assert first == second == known and first.startswith("Работа остановлена")
    assert len(await all_rows(session_factory, Vacancy)) == 1


async def test_the_same_page_twice_is_a_repeat_and_costs_nothing(
    make_pipeline, session_factory, one_vector, parsed
):
    """Повтор по номеру узнаётся до модели эмбеддингов: ни вызова, ни второго разбора."""
    job, tools, _ = await _seeker(make_pipeline, session_factory)
    submit = tool(tools, "submit_vacancy")
    await submit(text="Текст", url=PAGE, published="", contacts=[])

    answer = await submit(text="Текст", url=PAGE, published="", contacts=[])

    assert answer.startswith("повтор") and job.submitted == 1
    assert len(one_vector) == 1 and len(parsed) == 1


async def test_a_page_of_another_site_is_refused(make_pipeline, session_factory):
    _, tools, _ = await _seeker(make_pipeline, session_factory)

    answer = await tool(tools, "submit_vacancy")(
        text="Текст", url="https://other.test/vacancy/1", published="", contacts=[]
    )

    assert answer.startswith("пропущена") and await all_rows(session_factory, Vacancy) == []


async def test_a_silent_embedding_model_refuses(make_pipeline, session_factory, silent_embedder):
    job, tools, _ = await _seeker(make_pipeline, session_factory)

    answer = await tool(tools, "submit_vacancy")(text="Текст", url=PAGE, published="", contacts=[])

    assert answer.startswith("отказ") and job.refused


async def test_the_limit_stops_new_submissions(make_pipeline, session_factory):
    _, tools, _ = await _seeker(make_pipeline, session_factory, limit=0)

    answer = await tool(tools, "submit_vacancy")(text="Текст", url=PAGE, published="", contacts=[])

    assert answer.startswith("предел исчерпан") and await all_rows(session_factory, Vacancy) == []


async def test_a_page_like_a_parsed_vacancy_is_a_repeat(make_pipeline, session_factory, parsed):
    """Та же вакансия с другого источника — повтор: вторую строку не заводят и не разбирают."""
    known = vacancy_row(is_parsed=True, embedding=[0.1, 0.2])
    await put(session_factory, known)
    job, tools, kit = await _seeker(make_pipeline, session_factory)

    answer = await tool(tools, "submit_vacancy")(text="Текст", url=PAGE, published="", contacts=[])

    assert answer.startswith("повтор") and job.submitted == 0
    assert [v.id for v in await all_rows(session_factory, Vacancy)] == [known.id]
    assert parsed == [] and kit.browser.calls == []


async def test_a_page_like_an_unparsed_vacancy_finishes_it(make_pipeline, session_factory, parsed):
    """Похожая брошена недоразобранной — её дочитывают текстом найденной страницы
    и ведут дальше по циклу."""
    known = vacancy_row(is_parsed=False, embedding=[0.1, 0.2])
    await put(session_factory, known)
    _, tools, kit = await _seeker(make_pipeline, session_factory)

    answer = await tool(tools, "submit_vacancy")(text="Полный текст", url=PAGE, published="", contacts=[])

    assert answer.startswith("повтор") and "browser_open" in answer
    assert parsed == [(known.id, "Полный текст", None, True)]
    assert kit.pipeline.applied == [[known.id]]


BARRED_PAGE = "https://jobs.barred.test/vacancy/1"


async def _web_seeker(make_pipeline, session_factory):
    """Искатель «Поиска по сети», а у человека в отсеве сайт `barred.test`."""
    await put(session_factory, blacklist_row("aggregator", "barred.test"))
    job, tools, _ = await _seeker(make_pipeline, session_factory, row=web_search_row())
    return job, tools


async def test_a_page_of_a_blacklisted_site_is_not_to_be_opened(make_pipeline, session_factory):
    _, tools = await _web_seeker(make_pipeline, session_factory)

    answer = await tool(tools, "is_known")(url=BARRED_PAGE)

    assert "чёрном списке" in answer and "не открывай" in answer


async def test_a_page_of_a_blacklisted_site_is_skipped_without_costing_the_limit(
    make_pipeline, session_factory
):
    """Не отказ — отказ обрывает обход; сайт в отсеве лишь пропускается."""
    job, tools = await _web_seeker(make_pipeline, session_factory)

    answer = await tool(tools, "submit_vacancy")(
        text="Текст вакансии", url=BARRED_PAGE, published="", contacts=[]
    )

    assert answer.startswith("пропущена") and "чёрном списке" in answer
    assert (await all_rows(session_factory, Vacancy), job.submitted, job.refused) == ([], 0, False)


@pytest.mark.parametrize("url", [
    "https://t.me/jobs_channel/15",
    "https://www.telegram.me/jobs_channel/15",
    "https://telegra.ph/Vacancy-10-18",
])
async def test_a_telegram_page_is_left_to_its_own_round(make_pipeline, session_factory, url):
    """Каналы читает приём постов, их статьи он же дочитывает: «Поиску по сети»
    туда не нужно, и это не чёрный список человека."""
    job, tools = await _web_seeker(make_pipeline, session_factory)

    known = await tool(tools, "is_known")(url=url)
    answer = await tool(tools, "submit_vacancy")(
        text="Текст вакансии", url=url, published="", contacts=[]
    )

    assert "свой обход" in known and "чёрном списке" not in known
    assert answer.startswith("пропущена") and "свой обход" in answer
    assert (await all_rows(session_factory, Vacancy), job.submitted) == ([], 0)
