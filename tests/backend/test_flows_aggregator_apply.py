"""Фаза 2: отклик способ за способом, пока один не удался или способы не кончились."""

import pytest

from backend.flows.aggregator_apply import ApplyOrder, apply_phase, apply_vacancy
from backend.flows.aggregator_round import RoundState
from backend.models import Vacancy, VacancyStatus
from tests.backend.fixtures.applying import FORM, PAGE
from tests.dbio import all_rows, put
from tests.factories import vacancy_row
from tests.fakes.agent import fail_step, finish_step, record_step, scripted_kit


@pytest.fixture
def applying(make_pipeline):
    """Отклик по сценарию; ответ — итог, водитель и состояние обхода."""

    async def run(vacancy_id, steps, round_=None):
        kit = scripted_kit(await make_pipeline(), steps)
        driver = kit.run_session
        round_ = round_ or RoundState(set(), web_search_id=0)
        return await apply_vacancy(kit, round_, ApplyOrder(vacancy_id, None)), driver, round_

    return run


async def test_the_first_way_that_works_ends_the_vacancy(board, applying, session_factory):
    _, vacancy = await board()

    outcome, driver, _ = await applying(vacancy.id, [record_step(PAGE, via="aggregator")])

    assert outcome == "applied" and len(driver.plans) == 1
    (stored,) = await all_rows(session_factory, Vacancy)
    assert stored.status is VacancyStatus.APPLIED


async def test_a_failed_way_hands_over_to_the_next(board, applying, session_factory):
    _, vacancy = await board()

    outcome, driver, _ = await applying(vacancy.id, [fail_step("капча"), fail_step("форма сломана")])

    assert outcome == "exhausted" and len(driver.plans) == 2
    (stored,) = await all_rows(session_factory, Vacancy)
    assert stored.status is VacancyStatus.NEW


async def test_a_closed_platform_drops_its_button_for_the_rest_of_the_round(
    board, applying, session_factory
):
    site, vacancy = await board()
    second = vacancy_row(status=VacancyStatus.NEW, source_aggregator_id=site.id,
                         source_key="vacancy/2", source_url="https://site.test/vacancy/2")
    await put(session_factory, second)

    _, _, round_ = await applying(vacancy.id, [finish_step("platform_closed"), fail_step("нет")])
    _, driver, _ = await applying(second.id, [], round_=round_)

    assert round_.closed_aggregators == {site.id}
    assert driver.plans == []


async def test_a_crashed_way_is_missed_and_the_next_way_is_tried(board, applying):
    _, vacancy = await board()

    async def crash(tools):
        raise RuntimeError("сломалось")

    outcome, driver, _ = await applying(vacancy.id, [crash, record_step(FORM)])

    assert outcome == "applied" and len(driver.plans) == 2


async def test_the_phase_skips_vacancies_that_left_new(board, make_pipeline):
    _, vacancy = await board(status=VacancyStatus.NOT_FIT)
    kit = scripted_kit(await make_pipeline(), [])
    driver = kit.run_session

    await apply_phase(kit, RoundState(set(), web_search_id=0), [vacancy.id])

    assert driver.plans == []


async def test_the_phase_skips_vacancies_left_unparsed(board, make_pipeline):
    """Не разобранная — без балла и приговора: откликаться на неё рано."""
    _, vacancy = await board(is_parsed=False)
    kit = scripted_kit(await make_pipeline(), [])
    driver = kit.run_session

    await apply_phase(kit, RoundState(set(), web_search_id=0), [vacancy.id])

    assert driver.plans == []
