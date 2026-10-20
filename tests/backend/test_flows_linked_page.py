"""Страница вакансии по ссылке: агент открывает её и заводит вакансию теми же
инструментами, что «Поиск по сети», заведённой человеком."""

import asyncio

import pytest

from backend.flows.handover import hand_made_intake
from backend.flows.hand_outcome import HandResult
from backend.flows.linked_page import ingest_page
from backend.models import Vacancy, VacancyEvent, VacancyStatus
from backend.repository.vacancies_new import HAND_MADE
from tests.dbio import all_rows, only_row, put
from tests.factories import blacklist_row, vacancy_row
from tests.factories_aggregators import aggregator_row, web_search_row
from tests.backend.fixtures.flows import told_then_applied
from tests.backend.fixtures.parse_stub import parse_into
from tests.fakes.agent import finish_step, scripted_kit, submit_step

pytestmark = pytest.mark.usefixtures("one_vector")

HH_PAGE = "https://hh.ru/vacancy/123"
COMPANY_PAGE = "https://company.test/careers/qa"


@pytest.fixture
async def page(make_pipeline, session_factory, parsed):
    """Завести страницу по ссылке сценарием агента; ответ — набор и вести окну."""
    web, hh = web_search_row(), aggregator_row(host="hh.ru", is_active=False)
    await put(session_factory, web, hh)

    async def run(url, steps, hands_over=False, on_kit=None):
        kit = scripted_kit(await make_pipeline(), steps)
        told_then_applied(kit.pipeline)
        if on_kit is not None:
            on_kit(kit)
        await ingest_page(kit, url, hand_made_intake(hands_over))
        return kit

    run.web, run.hh = web, hh
    return run


def _submitting(url):
    return submit_step(url, "Ищем QA в команду")


async def test_a_page_of_a_known_aggregator_goes_through_it(page, session_factory, parsed):
    """Страница заведённого агрегатора — его профилем, даже с выключенным обходом;
    строка — заведённая человеком, в New, без отклика по выключенному переключателю."""
    kit = await page(HH_PAGE, [_submitting(HH_PAGE)])

    saved = await only_row(session_factory, Vacancy)
    assert ("profile", page.hh.id) in kit.browser.calls
    assert (saved.source_aggregator_id, saved.source_url, saved.status) == (page.hh.id, HH_PAGE, VacancyStatus.NEW)
    (event,) = await all_rows(session_factory, VacancyEvent)
    assert event.kind == HAND_MADE and event.payload["via"] == "found"
    assert kit.pipeline.told == [HandResult("ok", saved.id)] and kit.pipeline.applied == []
    (plan,) = kit.run_session.plans
    assert HH_PAGE in plan.task


async def test_a_company_site_goes_as_the_open_web(page, session_factory, parsed):
    kit = await page(COMPANY_PAGE, [_submitting(COMPANY_PAGE)])

    saved = await only_row(session_factory, Vacancy)
    assert saved.source_aggregator_id == page.web.id
    assert ("profile", page.web.id) in kit.browser.calls


async def test_a_page_without_a_vacancy_is_said_so(page, session_factory):
    kit = await page(COMPANY_PAGE, [finish_step()])

    assert await all_rows(session_factory, Vacancy) == []
    assert kit.pipeline.told == [HandResult("no_vacancy")]


async def test_a_session_that_failed_is_not_a_page_without_a_vacancy(page, session_factory):
    """Сессия сорвалась — капча, вход, срок: это не «вакансии нет»; беду окну
    скажет бот по концу работы, где итога не прозвучало."""
    kit = await page(COMPANY_PAGE, [finish_step("failed", "капча")])

    assert kit.pipeline.told == []


async def test_the_page_seeker_only_submits(page):
    """Искать ему нечего: спрашивать, известна ли вакансия, незачем."""
    kit = await page(COMPANY_PAGE, [finish_step()])

    (plan,) = kit.run_session.plans
    names = {tool.__name__ for tool in plan.tools}
    assert "submit_vacancy" in names and "is_known" not in names


async def test_a_redirect_within_the_aggregator_is_still_this_page(page, session_factory, parsed):
    """Вставлен адрес поддомена площадки, а она увела на основной — это её
    страница, а не чужой сайт."""
    await page("https://spb.hh.ru/vacancy/123", [_submitting(HH_PAGE)])

    assert len(await all_rows(session_factory, Vacancy)) == 1


async def test_a_broken_parse_leaves_the_word_to_the_bot(page, session_factory, monkeypatch):
    """Беда цикла — запись в журнал и конец страницы; окну её скажет бот, а не
    «нет вакансии»."""
    def broken():
        raise RuntimeError("разбор упал")

    parse_into(monkeypatch, [], done=broken)

    kit = await page(COMPANY_PAGE, [_submitting(COMPANY_PAGE)])

    assert kit.pipeline.told == []


async def test_a_broken_apply_after_the_word_sends_no_second_word(page, session_factory, parsed):
    """Окно уже услышало «заведена»; сорвавшийся следом отклик второй вести не шлёт."""

    def watch(kit):
        async def apply(ids):
            raise RuntimeError("отклик сорвался")
        kit.pipeline.apply = apply

    kit = await page(COMPANY_PAGE, [_submitting(COMPANY_PAGE)], hands_over=True, on_kit=watch)

    saved = await only_row(session_factory, Vacancy)
    assert kit.pipeline.told == [HandResult("ok", saved.id)]


async def test_a_silent_embedder_tells_once_and_closes_the_page(page, session_factory, silent_embedder):
    answers = []

    async def step(tools):
        for _ in range(2):
            answers.append(await tools["submit_vacancy"](text="Текст", url=COMPANY_PAGE, published="", contacts=[]))
        await tools["finish"](result="done")

    kit = await page(COMPANY_PAGE, [step])

    assert kit.pipeline.told == [HandResult("embed")]
    assert "предел исчерпан" in answers[1]


async def test_a_same_source_unparsed_row_is_replaced(page, session_factory, parsed):
    """Недоразобранная того же источника прав не имеет: её сносят и заводят
    страницу заново."""
    stale = vacancy_row(source_aggregator_id=page.web.id, source_key="company.test/careers/qa",
                        is_parsed=False, raw_text="старый текст")
    await put(session_factory, stale)

    kit = await page(COMPANY_PAGE, [_submitting(COMPANY_PAGE)])

    saved = await only_row(session_factory, Vacancy)
    assert saved.raw_text == "Ищем QA в команду" and kit.pipeline.told == [HandResult("ok", saved.id)]


async def test_a_vacancy_of_another_site_is_not_this_page(page, session_factory):
    """Переадресация на другой сайт — не та страница: вакансии на ней нет."""
    answers = []

    async def step(tools):
        answers.append(await tools["submit_vacancy"](
            text="Текст", url="https://other.test/jobs/1", published="", contacts=[]))
        await tools["finish"](result="done")

    kit = await page(COMPANY_PAGE, [step])

    assert answers[0].startswith("не та страница")
    assert await all_rows(session_factory, Vacancy) == []
    assert kit.pipeline.told == [HandResult("no_vacancy")]


async def test_a_blacklisted_site_is_filed_by_hand(page, session_factory, parsed):
    """Чёрный список — подсказка автоматике: человек завёл — значит, хочет."""
    await put(session_factory, blacklist_row("aggregator", "company.test"))

    await page(COMPANY_PAGE, [_submitting(COMPANY_PAGE)])

    assert len(await all_rows(session_factory, Vacancy)) == 1


async def test_a_page_like_an_orphan_gets_its_own_row(page, session_factory, parsed):
    """Сходство однозначного повтора не даёт: своя строка, брошенная похожая цела."""
    orphan = vacancy_row(is_parsed=False, embedding=[0.1, 0.25], raw_text="Ищем QA")
    await put(session_factory, orphan)

    await page(COMPANY_PAGE, [_submitting(COMPANY_PAGE)])

    assert len(await all_rows(session_factory, Vacancy)) == 2
    assert orphan.id not in [one[0] for one in parsed]


async def test_a_page_of_the_same_source_filed_before_is_a_duplicate(page, session_factory, parsed):
    """Адрес без шаблона площадки ключа не даёт, но та же страница того же
    источника — тот же номер (`source_key`): повтор с номером существующей."""
    existing = vacancy_row(source_aggregator_id=page.web.id, source_key="company.test/careers/qa")
    await put(session_factory, existing)

    kit = await page(COMPANY_PAGE, [_submitting(COMPANY_PAGE)])

    assert len(await all_rows(session_factory, Vacancy)) == 1
    assert kit.pipeline.told == [HandResult("duplicate", existing.id)]


async def test_the_switch_hands_the_page_over_after_new(page, session_factory, parsed):
    kit = await page(COMPANY_PAGE, [_submitting(COMPANY_PAGE)], hands_over=True)

    saved = await only_row(session_factory, Vacancy)
    assert kit.pipeline.applied == [[saved.id]]


async def test_the_nested_apply_is_not_counted_in_the_session(page, parsed, short_clock):
    """Отклик дольше всего срока сессии доходит до конца: вложенный цикл в срок
    страницы не идёт, и гасить её посреди отклика некому."""
    applied = []

    def watch(kit):
        async def apply(ids):
            await asyncio.sleep(0.2)
            applied.append(ids)
        kit.pipeline.apply = apply

    await page(COMPANY_PAGE, [_submitting(COMPANY_PAGE)], hands_over=True, on_kit=watch)

    assert len(applied) == 1


async def test_the_bar_shows_the_parse_of_an_ad(page, parsed):
    steps = []

    def watch(kit):
        kit.pipeline.on_progress = lambda *step: steps.append(step)

    await page(COMPANY_PAGE, [_submitting(COMPANY_PAGE)], on_kit=watch)

    assert steps and all(step[:2] == ("hand_made", "Разбор объявления") for step in steps)
