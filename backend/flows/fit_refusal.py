"""Отказ в пригодности: пост не вакансия, мимо анкеты по полям или по суждению модели.

Отличие от соседа `flows/parse`: тот выносит приговор объявлению целиком —
разбор, чёрный список, мусор, запись исхода, — а здесь только вопрос «годится
ли разобранное человеку» и беды зовов к модели, которые на него отвечают.
"""

import logging

from adapters.lm_chat import MODEL_REFUSED
from backend.domain.fit_fields import grade_refusal, work_format_refusal
from backend.domain.verdict import (
    LLM_SKIP_PREFIX,
    REFUSED_SKIP_REASON,
    TRASH_SKIP_PREFIX,
    TRUNCATED_SKIP_REASON,
)
from backend.llm.answers import TRUNCATED_TROUBLE
from backend.llm.fit_languages import validate_language_fit
from backend.llm.fit_place import validate_place_fit
from backend.llm.fit_preferences import validate_preferences_fit
from backend.llm.fit_role import validate_role_fit
from backend.llm.genre import classify_post_genre

logger = logging.getLogger(__name__)


def unanswered(
    what: str, trouble: str | None, vacancy_id: int
) -> tuple[str | None, bool] | None:
    """Что делать с бедой при обращении к модели; пусто — беды не было.

    Обрыв по пределу токенов и молчание провайдера решают разное, и все зовы к
    модели — о разборе, о жанре и о пригодности — разводят их одинаково.
    Обрыв повторится и на втором заходе с запасом, отказ модели — на том же
    тексте, значит дальше это дело человека: строка ложится в окно с
    названной причиной. Молчание провайдера приговором не является вовсе —
    строка остаётся неразобранной и ждёт следующего захода.
    """
    if trouble is None:
        return None
    if trouble == TRUNCATED_TROUBLE:
        logger.warning(
            "vacancy %s: %s не поместился даже с запасом, отдаю человеку",
            vacancy_id, what,
        )
        return TRUNCATED_SKIP_REASON, False
    if trouble == MODEL_REFUSED:
        logger.warning("vacancy %s: модель отказалась отвечать на %s, отдаю человеку", vacancy_id, what)
        return REFUSED_SKIP_REASON, False
    logger.warning(
        "vacancy %s: %s не спросился (%s), оставляю неразобранной",
        vacancy_id, what, trouble,
    )
    return None, True


def _fit_verdict_refusal(validation) -> str | None:
    """Причина отказа по вердикту одного зова; пусто — этот зов не возражает.

    Неразобранный ответ считается отказом нарочно: закрытая дверь тут дешевле
    открытой — человек пересмотрит вакансию руками, а вот отклик, ушедший по
    невнятному вердикту, не отзовёшь.

    Метки мусора эти отказы не получают никогда, каким бы ни был вердикт:
    вакансия ли это, решено раньше и другим зовом, а метка мусора разрешает
    удалить строку насовсем.
    """
    if validation is None:
        logger.warning("вердикт о пригодности не прочитался, помечаю Not Fit")
        return f"{LLM_SKIP_PREFIX}validation unavailable"
    if validation.verdict == "fit":
        return None
    return f"{LLM_SKIP_PREFIX}{validation.reason or 'rejected'}"


async def _fit_refusal(
    pipeline, parsed, text: str, vacancy_id: int
) -> tuple[str | None, bool]:
    """Причина, по которой вакансия отвергнута, и «спросить не вышло».

    Пустая причина значит «годится». Второе значение отделяет от неё беду
    провайдера: по ней приговора нет вовсе, и строку нельзя помечать
    разобранной — лежащий полчаса провайдер иначе уводит в «не подходит» всё,
    что пришло за это время, а вернуть их можно только кнопкой по каждой.

    Зовы — роль, языки, место, свободные предпочтения, — и первый отказ
    прекращает остальные: за них платят токенами и временем, а приговор уже
    вынесен. Порознь они стоят потому, что зов не ошибётся о том, чего ему не
    давали: в общем зове запрет из одного критерия переносится на другой.
    """
    for ask in (validate_role_fit, validate_language_fit, validate_place_fit, validate_preferences_fit):
        validation, trouble = await ask(
            parsed,
            text,
            pipeline.lm_client,
            pipeline.lm_chat_model,
            profile=pipeline.profile_cache,
        )
        logger.debug(
            "vacancy %s: %s verdict=%s reason=%r",
            vacancy_id,
            ask.__name__,
            validation.verdict if validation else None,
            validation.reason if validation else None,
        )
        trouble_answer = unanswered("вердикт", trouble, vacancy_id)
        if trouble_answer is not None:
            return trouble_answer
        refusal = _fit_verdict_refusal(validation)
        if refusal is not None:
            return refusal, False
    return None, False


async def _genre_refusal(
    pipeline, text: str, vacancy_id: int
) -> tuple[str | None, bool]:
    """Метка мусора, если пост не вакансия, и «спросить не вышло».

    Спрашивают об одном — о жанре, — и без анкеты кандидата вовсе: похожесть
    поста на анкету не должна влиять на ответ. Неразобранный ответ приговором
    не считается и пропускает пост дальше: по нему нельзя удалять, а следом
    стоит вердикт о пригодности.
    """
    genre, trouble = await classify_post_genre(
        text, pipeline.lm_client, pipeline.lm_chat_model, pipeline.profile_cache.user_language
    )
    trouble_answer = unanswered("жанр", trouble, vacancy_id)
    if trouble_answer is not None:
        return trouble_answer
    if genre is None or genre.is_vacancy:
        return None, False
    logger.info("vacancy %s: не вакансия — %s", vacancy_id, genre.reason)
    return f"{TRASH_SKIP_PREFIX}{genre.reason}", False


def _fields_refusal(parsed, profile) -> str | None:
    """Отказ по полям-перечислениям; пусто — эти поля не мешают.

    Стоит перед зовами к модели, потому что не стоит ничего: обе стороны
    здесь перечисления, и первый же отказ избавляет от всех обращений к
    провайдеру. Причина звучит так же, как у отказа модели, — требованием
    вакансии («Требуется грейд …»), без приставки: окно показывает незнакомую
    строку как есть.
    """
    return grade_refusal(parsed.grade, profile.grades) or work_format_refusal(
        parsed.remote, profile.work_formats
    )


async def unfit_refusal(
    pipeline, parsed, text: str, vacancy_id: int
) -> tuple[str | None, bool]:
    """Чем объявление отвергнуто: жанр, поля-перечисления, зовы о смысле.

    Вопросы разведены по зовам нарочно. Слитые в один, они спорят: на посте,
    похожем на анкету кандидата, «подходит ли» перебивает «вакансия ли это»,
    и резюме получает «годится». Тем же доводом расщеплена и сама
    пригодность — на роль, языки, место и свободные предпочтения.

    Порядок выбран по цене: бесплатные проверки идут раньше платных, и первый
    отказ прекращает остальные.
    """
    refusal, unasked = await _genre_refusal(pipeline, text, vacancy_id)
    if unasked or refusal is not None:
        return refusal, unasked
    by_fields = _fields_refusal(parsed, pipeline.profile_cache)
    if by_fields is not None:
        logger.info("vacancy %s: не подходит по полям — %s", vacancy_id, by_fields)
        return by_fields, False
    return await _fit_refusal(pipeline, parsed, text, vacancy_id)
