"""Что становится с объявлением, когда модель не дала ответа.

Беды бывают трёх родов, и последствия у них разные. Молчание поставщика
временно: строка остаётся неразобранной и ждёт следующего захода. Обрыв ответа
даже с запасом и отказ модели повторятся на том же тексте: строка ложится
человеку с названной причиной и разбирается заново по кнопке.
"""

from adapters.lm_chat import MODEL_REFUSED
from backend.domain.verdict import REFUSED_SKIP_REASON, TRUNCATED_SKIP_REASON
from backend.flows import parse
from backend.llm.answers import TRUNCATED_TROUBLE
from backend.models import TrashEvent, Vacancy, VacancyStatus
from tests.dbio import all_rows, only_row


async def test_a_vacancy_survives_a_provider_that_did_not_answer(
    parsing, session_factory
):
    """Не ответивший провайдер объявление не выбрасывает.

    Отказ модели и приговор «это не вакансия» — разные вещи, и удалять
    строку имеет право только второй. Наблюдается это тем, что чужой
    приговор из обстановки остался нетронутым: своего разбор не выносил,
    а значит строку подберёт следующий заход.
    """
    pipeline, vacancy = parsing
    pipeline.parsed = None
    pipeline.parse_refusal = "empty_content"

    done = await parse.parse_and_update_vacancy(
        pipeline, vacancy.id, "текст", "jobs", allow_delete=True
    )

    saved = await only_row(session_factory, Vacancy)
    assert saved.id == vacancy.id
    assert saved.is_parsed is False
    # Чужой приговор из обстановки — на месте: своего разбор не выносил.
    assert saved.skip_reason == "прошлый отказ"
    assert await all_rows(session_factory, TrashEvent) == []
    assert done is False


async def test_a_verdict_that_never_fits_lands_the_vacancy_for_the_human(
    parsing, session_factory
):
    """Не поместившийся вердикт кладёт строку человеку, а не в вечный круг.

    Объявление к этому мигу разобрано — приговора нет только у пригодности, и
    переспросить с поднятым потолком модель уже пробовала. Оставь мы строку
    неразобранной, подбор брал бы её при каждом запуске и платил полным
    разбором; оставь «новой» — отклик ушёл бы по вакансии, которую никто не
    проверял.
    """
    pipeline, vacancy = parsing
    pipeline.verdict = None
    pipeline.fit_trouble = TRUNCATED_TROUBLE

    done = await parse.parse_and_update_vacancy(
        pipeline, vacancy.id, "текст", "jobs"
    )

    saved = await only_row(session_factory, Vacancy)
    assert done is True
    assert saved.is_parsed is True
    assert saved.status is VacancyStatus.NOT_FIT
    assert saved.skip_reason == TRUNCATED_SKIP_REASON


async def test_a_verdict_the_model_refused_lands_the_vacancy_for_the_human(
    parsing, session_factory
):
    """Отказ модели отвечать кладёт строку человеку, как и обрыв ответа.

    Отказ не временная беда поставщика: тот же текст получит тот же отказ, и
    неразобранная строка спрашивалась бы на каждом обороте, тратя лимит.
    """
    pipeline, vacancy = parsing
    pipeline.verdict = None
    pipeline.fit_trouble = MODEL_REFUSED

    done = await parse.parse_and_update_vacancy(
        pipeline, vacancy.id, "текст", "jobs"
    )

    saved = await only_row(session_factory, Vacancy)
    assert done is True
    assert saved.is_parsed is True
    assert saved.status is VacancyStatus.NOT_FIT
    assert saved.skip_reason == REFUSED_SKIP_REASON


async def test_a_verdict_nobody_answered_leaves_the_vacancy_unparsed(
    parsing, session_factory
):
    """Вердикт, которого не у кого спросить, оставляет вакансию неразобранной.

    Провайдер лежит целыми пачками: запиши мы такие вакансии в «не подходит» с
    пометкой «вердикт недоступен», вернуть их могла бы только кнопка по каждой.
    Неразобранную строку подберёт следующий заход сам.
    """
    pipeline, vacancy = parsing
    pipeline.verdict = None
    pipeline.fit_trouble = "llm_request_error"

    done = await parse.parse_and_update_vacancy(
        pipeline, vacancy.id, "текст", "jobs"
    )

    saved = await only_row(session_factory, Vacancy)
    assert saved.is_parsed is False
    # Чужой приговор из обстановки — на месте: своего разбор не выносил.
    assert saved.skip_reason == "прошлый отказ"
    assert done is False


async def test_a_post_the_genre_call_could_not_judge_stays_unparsed(parsing, session_factory):
    """Не спросившийся жанр приговора не выносит — строка ждёт следующего раза.

    Лежащий провайдер иначе уводил бы в мусор всё, что пришло за это время, а
    удаление необратимо.
    """
    pipeline, vacancy = parsing
    pipeline.genre_trouble = "provider is down"

    done = await parse.parse_and_update_vacancy(
        pipeline, vacancy.id, "текст", "jobs", allow_delete=True
    )

    assert done is False
    assert pipeline.validated is False
    saved = await only_row(session_factory, Vacancy)
    assert saved.is_parsed is False
    assert saved.skip_reason == "прошлый отказ"


async def test_a_genre_answer_that_never_fits_is_handed_to_the_person(
    parsing, session_factory
):
    """Не поместившийся ответ о жанре отдают человеку, а не оставляют навсегда.

    Обрыв по пределу токенов повторится и на втором заходе с запасом: строка
    иначе разбиралась бы заново каждый оборот и не разобралась бы никогда.
    """
    pipeline, vacancy = parsing
    pipeline.genre_trouble = TRUNCATED_TROUBLE

    await parse.parse_and_update_vacancy(pipeline, vacancy.id, "текст", "jobs", allow_delete=False)

    saved = await only_row(session_factory, Vacancy)
    assert pipeline.validated is False
    assert saved.skip_reason == TRUNCATED_SKIP_REASON
