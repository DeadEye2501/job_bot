"""Разбор вакансии, заведённой человеком: поля заполняются, приговора нет.

Человек её добавил — значит, хочет откликнуться; анкета, чёрный список и порог
балла — подсказка автоматике, и в Not Fit такая вакансия только потерялась бы.
"""

import pytest

from adapters.lm_chat import MODEL_REFUSED
from backend.flows import parse, rerun
from backend.llm.answers import TRUNCATED_TROUBLE
from backend.models import Vacancy, VacancyStatus
from backend.payloads import PostGenre
from backend.repository.vacancies_new import HAND_MADE
from tests.dbio import only_row, put
from tests.factories import parsed_vacancy, vacancy_event_row


@pytest.fixture
async def by_hand(parsing, session_factory):
    pipeline, vacancy = parsing
    await put(session_factory, vacancy_event_row(vacancy.id, kind=HAND_MADE))
    return pipeline, vacancy


async def test_a_vacancy_below_the_threshold_stays_new(by_hand, session_factory):
    pipeline, vacancy = by_hand
    await pipeline.rs.set_app("scoring_threshold", "100")

    judged = await parse.parse_and_update_vacancy(pipeline, vacancy.id, "Python", None)

    saved = await only_row(session_factory, Vacancy)
    assert judged.stored and saved.is_parsed
    assert (saved.status, saved.skip_reason, saved.title) == (VacancyStatus.NEW, None, "Python-разработчик")


async def test_the_fit_of_a_hand_made_vacancy_is_not_asked(by_hand, session_factory):
    """«Вакансия ли это» и пригодность по анкете не спрашиваются вовсе — не
    «спросить и переписать», а не звать."""
    pipeline, vacancy = by_hand
    pipeline.genre = PostGenre(is_vacancy=False, reason="это реклама курсов")

    await parse.parse_and_update_vacancy(pipeline, vacancy.id, "Python", None)

    assert (await only_row(session_factory, Vacancy)).status == VacancyStatus.NEW
    assert (pipeline.genre_asked, pipeline.fit_asked) == (False, [])


async def test_a_blacklisted_word_does_not_stop_a_hand_made_vacancy(by_hand, session_factory):
    pipeline, vacancy = by_hand
    pipeline.blacklist_patterns = ["казино"]

    await parse.parse_and_update_vacancy(pipeline, vacancy.id, "Ищем в казино", None)

    saved = await only_row(session_factory, Vacancy)
    assert (saved.status, saved.skip_reason) == (VacancyStatus.NEW, None)


async def test_a_resume_mark_does_not_throw_a_hand_made_vacancy_out(by_hand, session_factory):
    pipeline, vacancy = by_hand

    await parse.parse_and_update_vacancy(pipeline, vacancy.id, "#cv Позиция: Python Developer", None)

    saved = await only_row(session_factory, Vacancy)
    assert (saved.status, saved.skip_reason) == (VacancyStatus.NEW, None)


async def test_an_empty_parse_of_a_hand_made_vacancy_is_not_deleted(by_hand, session_factory):
    pipeline, vacancy = by_hand
    pipeline.parsed = parsed_vacancy(title="Хоть что-то")

    judged = await parse.parse_and_update_vacancy(pipeline, vacancy.id, "текст", None, allow_delete=True)

    saved = await only_row(session_factory, Vacancy)
    assert judged.stored
    assert (saved.status, saved.skip_reason, saved.is_parsed) == (VacancyStatus.NEW, None, True)


@pytest.mark.parametrize("trouble", [TRUNCATED_TROUBLE, MODEL_REFUSED], ids=["обрыв", "отказ модели"])
async def test_a_model_that_gave_up_leaves_a_hand_made_vacancy_new(by_hand, session_factory, trouble):
    pipeline, vacancy = by_hand
    pipeline.parse_refusal = trouble

    await parse.parse_and_update_vacancy(pipeline, vacancy.id, "текст", None, allow_delete=True)

    saved = await only_row(session_factory, Vacancy)
    assert (saved.status, saved.skip_reason, saved.is_parsed) == (VacancyStatus.NEW, None, True)


async def test_a_silent_provider_leaves_a_hand_made_vacancy_unparsed(by_hand, session_factory):
    """Молчание провайдера — не приговор и у ручного: строка ждёт следующего захода."""
    pipeline, vacancy = by_hand
    pipeline.parse_refusal = "модель не ответила"

    judged = await parse.parse_and_update_vacancy(pipeline, vacancy.id, "текст", None)

    assert not judged.stored
    assert not (await only_row(session_factory, Vacancy)).is_parsed


async def test_the_automatic_vacancy_is_still_judged(parsing, session_factory):
    """Признак — событие своего рода, а не всякое событие ленты."""
    pipeline, vacancy = parsing
    await put(session_factory, vacancy_event_row(vacancy.id, kind="ingested"))
    await pipeline.rs.set_app("scoring_threshold", "100")

    await parse.parse_and_update_vacancy(pipeline, vacancy.id, "Python", "jobs")

    assert (await only_row(session_factory, Vacancy)).status == VacancyStatus.NOT_FIT


async def test_the_recovery_parses_a_hand_made_row_but_does_not_hand_it_over(by_hand, session_factory):
    """Положение переключателя жило в памяти окна: брошенную строку человека
    подбор дочитывает, но откликателю не отдаёт."""
    pipeline, vacancy = by_hand

    assert await pipeline.recover_orphan_vacancies() == 1

    assert (await only_row(session_factory, Vacancy)).status == VacancyStatus.NEW
    assert pipeline.applied == []


async def test_a_rerun_of_a_hand_made_vacancy_hands_it_over(by_hand):
    """«Прогнать заново» — нажатие человека: передача по режиму, как прежде."""
    pipeline, vacancy = by_hand

    assert await rerun.rerun_pipeline_for_vacancy(pipeline, vacancy.id) == "ok"

    assert pipeline.applied == [[vacancy.id]]
