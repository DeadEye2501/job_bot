"""Сбор отдаёт откликателю: годная после вердикта вакансия уходит отклику, догон
нового HR — после отклика."""

from backend.flows import handover, parse
from backend.flows.handover import judge_and_hand_over, new_to_apply
from backend.models import Vacancy, VacancyStatus
from tests.dbio import put
from tests.factories import at, parsed_vacancy, vacancy_row


async def _set_status(session_factory, vacancy_id, status):
    async with session_factory() as session:
        (await session.get(Vacancy, vacancy_id)).status = status
        await session.commit()


async def test_a_fit_vacancy_goes_to_the_applier(parsing):
    pipeline, vacancy = parsing
    assert await judge_and_hand_over(pipeline, vacancy.id, "Python", "chan")
    assert pipeline.applied == [[vacancy.id]]


async def test_an_unfit_vacancy_stays_with_the_collection(parsing):
    pipeline, vacancy = parsing
    await pipeline.rs.set_app("scoring_threshold", "100")
    await judge_and_hand_over(pipeline, vacancy.id, "Python", "chan")
    assert pipeline.applied == []


async def test_a_parse_the_model_never_answered_applies_nothing(parsing):
    """Без ответа модели вакансия остаётся в New неразобранной — откликаться рано."""
    pipeline, vacancy = parsing
    pipeline.parse_refusal = "модель не ответила"
    assert not await judge_and_hand_over(pipeline, vacancy.id, "Python", "chan")
    assert pipeline.applied == []


async def test_parsing_alone_applies_nothing(parsing):
    pipeline, vacancy = parsing
    await parse.parse_and_update_vacancy(pipeline, vacancy.id, "Python", "chan")
    assert pipeline.applied == []


async def test_a_new_hr_is_caught_up_after_the_application(parsing, monkeypatch):
    """Догон, пошедший первым, положил бы наше письмо в переписку без вакансии."""
    pipeline, vacancy = parsing
    pipeline.parsed = parsed_vacancy(
        title="Python-разработчик", stack_required=["Python"], hr_contact="@maria")
    order = []

    async def apply(ids):
        order.append("apply")

    pipeline.apply = apply
    monkeypatch.setattr(handover, "spawn_hr_backfill", lambda _p, hr: order.append("backfill"))
    await judge_and_hand_over(pipeline, vacancy.id, "Python", "chan")
    assert order == ["apply", "backfill"]


async def test_new_vacancies_to_apply_are_parsed_ones_newest_first(session_factory):
    """Неразобранная ещё не прошла отбор, а ушедшая из New уже не ждёт отклика."""
    old = vacancy_row(status=VacancyStatus.NEW, is_parsed=True, created_at=at(0))
    fresh = vacancy_row(status=VacancyStatus.NEW, is_parsed=True, created_at=at(10))
    raw = vacancy_row(status=VacancyStatus.NEW, is_parsed=False, created_at=at(20))
    done = vacancy_row(status=VacancyStatus.APPLIED, is_parsed=True, created_at=at(30))
    await put(session_factory, old, fresh, raw, done)

    assert await new_to_apply(session_factory) == [fresh.id, old.id]


async def test_a_rerun_of_an_applied_vacancy_applies_again(parsing, session_factory):
    pipeline, vacancy = parsing
    await _set_status(session_factory, vacancy.id, VacancyStatus.APPLIED)
    await judge_and_hand_over(pipeline, vacancy.id, "Python", "chan", allow_delete=False)
    assert pipeline.applied == [[vacancy.id]]
