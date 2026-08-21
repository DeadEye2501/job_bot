"""Приговор объявлению: разбор моделью, вердикт по разобранному и что дальше.

Всё здесь про одно — чем объявление кончилось: спросить модель, свериться с
чёрным списком, вынести приговор, выбросить мусор, отправить отклик пригодному,
пометить пустышку. Куда исход ложится, знает сосед (`flows/parse_write`);
зовут его отсюда, а не наоборот.
"""

import logging

from backend.flows import dm_backfill
from backend.domain.blacklist import check_blacklist
from backend.domain.fit_fields import grade_refusal, work_format_refusal
from backend.domain.resume_marks import resume_mark
from backend.domain.scoring import score_parsed
from backend.domain.verdict import blacklist_refusal, decide_vacancy_status
from backend.domain.verdict import is_empty_vacancy
from backend.domain.verdict import (
    EMPTY_SKIP_REASON,
    LLM_SKIP_PREFIX,
    TRASH_SKIP_PREFIX,
    TRUNCATED_SKIP_REASON,
)
from backend.llm.answers import TRUNCATED_TROUBLE
from backend.llm.fit_languages import validate_language_fit
from backend.llm.fit_preferences import validate_preferences_fit
from backend.llm.fit_role import validate_role_fit
from backend.llm.genre import classify_post_genre
from backend.llm.rules import VACANCY_TEXT_CHARS
from backend.llm.vacancy import parse_vacancy
from backend.models import Vacancy
from backend.payloads import ParsedVacancy
from backend.models import VacancyStatus
from backend.flows.events import record_vacancy_event

from backend.flows import apply
from backend.flows import cleanup
from backend.flows.parse_write import Outcome, persist_parse_outcome
from backend.repository.vacancy_status import was_ever_applied

logger = logging.getLogger(__name__)


async def _dropped_as_trash(
    pipeline, vacancy_id: int, reason: str, *, allow_delete: bool
) -> bool:
    """Убрать непригодную вакансию, если убирать разрешено; сказать, убрали ли.

    Приговор «непригодна» выносят трое — пустышке, метке соискательского
    поста и вердикту модели, — а развилка у них одна. Разрешение приходит
    доводом от зовущего и говорит об одном: ручается ли тот за текст, по
    которому вынесен приговор. Приём поста ручается, приговора без полного
    текста он и не выносит; подбор недоразобранного ручается за текст, полнее
    которого уже не станет. Прогон заново не разрешает никогда: строку человек
    открыл руками, и исчезнуть у него из-под курсора она не должна —
    непригодность остаётся пометкой в причине отказа.
    """
    if not allow_delete:
        logger.info(
            "vacancy %s: %s, marking Not Fit (deleting not allowed here)",
            vacancy_id, reason,
        )
        return False
    logger.info("vacancy %s: %s, deleting as trash", vacancy_id, reason)
    await cleanup.delete_vacancy_as_trash(pipeline, vacancy_id, reason=reason)
    return True


def _unanswered(
    what: str, trouble: str | None, vacancy_id: int
) -> tuple[str | None, bool] | None:
    """Что делать с бедой при обращении к модели; пусто — беды не было.

    Обрыв по пределу токенов и молчание провайдера решают разное, и все зовы к
    модели — о разборе, о жанре и три о пригодности — разводят их одинаково.
    Обрыв повторится и на втором заходе с запасом, значит дальше это дело
    человека: строка ложится в окно с названной причиной. Молчание провайдера
    приговором не является вовсе — строка остаётся неразобранной и ждёт
    следующего захода.
    """
    if trouble is None:
        return None
    if trouble == TRUNCATED_TROUBLE:
        logger.warning(
            "vacancy %s: %s не поместился даже с запасом, отдаю человеку",
            vacancy_id, what,
        )
        return TRUNCATED_SKIP_REASON, False
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

    Зовов три — роль, языки, свободные предпочтения, — и первый отказ
    прекращает остальные: за них платят токенами и временем, а приговор уже
    вынесен. Порознь они стоят потому, что зов не ошибётся о том, чего ему не
    давали: слитые в один, шесть критериев путались между собой — запрет из
    свободного текста применялся к месту, о котором в нём не было ни слова.
    """
    for ask in (validate_role_fit, validate_language_fit, validate_preferences_fit):
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
        unanswered = _unanswered("вердикт", trouble, vacancy_id)
        if unanswered is not None:
            return unanswered
        refusal = _fit_verdict_refusal(validation)
        if refusal is not None:
            return refusal, False
    return None, False


async def _thrown_out_as_a_resume(
    pipeline, vacancy_id: int, mark: str, allow_delete: bool
) -> bool:
    """Убрать пост соискателя, не спрашивая модель вовсе; сказать, вышло ли.

    Поля у такой строки не заполняются: разбора не было, а показывать в
    карточке разобранное прошлым заходом рядом с приговором «мусор» — значит
    выдавать старое за новое.
    """
    reason = f"{TRASH_SKIP_PREFIX}пост соискателя, метка {mark}"
    logger.info("vacancy %s: пост соискателя, метка %s", vacancy_id, mark)
    if await _dropped_as_trash(
        pipeline, vacancy_id, reason, allow_delete=allow_delete
    ):
        return True
    return await save_empty_vacancy(pipeline, vacancy_id, None, reason=reason)


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
        text, pipeline.lm_client, pipeline.lm_chat_model
    )
    unanswered = _unanswered("жанр", trouble, vacancy_id)
    if unanswered is not None:
        return unanswered
    if genre is None or genre.is_vacancy:
        return None, False
    logger.info("vacancy %s: не вакансия — %s", vacancy_id, genre.reason)
    return f"{TRASH_SKIP_PREFIX}{genre.reason}", False


def _fields_refusal(parsed, profile) -> str | None:
    """Отказ по полям-перечислениям; пусто — эти поля не мешают.

    Стоит перед зовами к модели, потому что не стоит ничего: обе стороны
    здесь перечисления, и первый же отказ избавляет от трёх обращений к
    провайдеру. Обоснование пишется той же формой, что требуется от модели, —
    требованием вакансии, — и приставки не получает: окно показывает
    незнакомую строку как есть.
    """
    return grade_refusal(parsed.grade, profile.grades) or work_format_refusal(
        parsed.remote, profile.work_formats
    )


async def _unfit_refusal(
    pipeline, parsed, text: str, vacancy_id: int
) -> tuple[str | None, bool]:
    """Чем объявление отвергнуто: жанр, поля-перечисления, три зова о смысле.

    Вопросы разведены по зовам нарочно. Слитые в один, они спорят: на посте,
    похожем на анкету кандидата, «подходит ли» перебивает «вакансия ли это»,
    и резюме получает «годится». Тем же доводом расщеплена и сама
    пригодность — на роль, языки и свободные предпочтения.

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


async def _auto_send_if_allowed(
    pipeline, hr, parsed, vacancy_id: int, status: VacancyStatus
) -> None:
    """Отправить отклик, если можно; попытку записать при любом исходе.

    Запись нужна затем, что через месяцы человек смотрит на новую вакансию
    с опознанным HR и пройденным порогом и не понимает, почему отклик так
    и не ушёл. Без строки в ленте ответа на это нет нигде — речь про исход
    самой отправки; те, до кого она не дошла вовсе, молчат, и ответ на них
    виден по другим следам: статусу, привязке HR, настройке автоотправки.

    У отбитого повтора след свой: три первых признака говорят «должно было
    уйти» — статус «Новая», HR привязан, автоотправка включена, — и объясняет
    молчание только история статусов, где отклик остался, вместе с записью
    «Прогон заново».

    «Уже откликались» спрашивается у истории, а не у статуса: разбор ставит
    начальный статус поверх любого, и прогон заново приводит сюда вакансию,
    у которой отклик давно ушёл, — со статусом «Новая», потому что его только
    что и поставили. Заслоны в `apply` читают статус и такую не отбивают вовсе.
    """
    if status != VacancyStatus.NEW or hr is None or not pipeline.rs.auto_apply:
        return
    async with pipeline.session_factory() as session:
        if await was_ever_applied(session, vacancy_id):
            logger.info(
                "vacancy %d: отклик уже уходил, второго письма не шлю", vacancy_id
            )
            return
    ok, reason = await apply.try_auto_send(pipeline, hr, parsed, vacancy_id)
    await record_vacancy_event(
        pipeline.session_factory,
        vacancy_id,
        "auto_send",
        {"ok": ok, "reason": reason},
    )


async def _parsed_or_dropped(
    pipeline, vacancy_id: int, text: str, channel_username: str, allow_delete: bool
):
    """Разобрать объявление; пустота в ответ — с ним уже покончено.

    Три значения: разбор, отказ модели и «дошла ли запись». Третье нужно
    только пустой дороге: там строку записывают, и сорвавшаяся запись не
    должна доехать до окна словом «разобрана».

    Пустышку отсеиваем до модели-оценщика: разбор не вытащил ни одного поля
    сверх названия, и второе обращение к модели ей не положено. Дорога эта не
    только для мемов, обрывков и рекламных строчек — сюда же наставление
    разбора сводит пост соискателя, веля отдать по нему пустоту вместо полей.
    Приговор «пусто» поэтому значит «вакансии тут нет», а не «мы не
    справились». Дальше две дороги — удалить или пометить, — и выбор между
    ними держит `_dropped_as_trash`.

    Не состоявшееся обращение к модели на эти дороги не выходит вовсе и
    отдаётся отдельно: приговора не было, значит и выбрасывать нечего.
    Строка остаётся неразобранной, за ней вернётся подбор недоразобранного.
    Удали её здесь — и пост не вернётся ничем: курсор канала уже сдвинут.
    """
    parsed, refusal = await parse_vacancy(
        text,
        pipeline.lm_client,
        pipeline.lm_chat_model,
        channel_username=channel_username,
        known_skills=pipeline.skills_cache,
    )
    trouble = _unanswered("разбор", refusal, vacancy_id)
    if trouble is not None:
        reason, unasked = trouble
        if unasked:
            return None, refusal, False
        return None, None, await save_empty_vacancy(
            pipeline, vacancy_id, None, reason=reason
        )
    if not is_empty_vacancy(parsed):
        return parsed, None, True
    if await _dropped_as_trash(
        pipeline, vacancy_id, EMPTY_SKIP_REASON, allow_delete=allow_delete
    ):
        return None, None, True
    return None, None, await save_empty_vacancy(pipeline, vacancy_id, parsed)


async def _verdict_for(
    pipeline, parsed, text: str, vacancy_id: int
) -> tuple | None:
    """Приговор объявлению: статус, причина отказа и баллы; пусто — не спросили.

    **Порог стоит за вопросом «вакансия ли это», а не перед ним.** Баллы
    отвечают, подходит ли вакансия кандидату, и к посту, вакансией не
    являющемуся, неприменимы: чужое резюме они отсеивают случайно, навыками
    мимо анкеты. На случайность начинают рассчитывать — отсев выглядит
    работающим фильтром ровно до того резюме, которое баллы наберёт, а по
    нему уходит письмо живому человеку.

    Чёрный список, наоборот, впереди: он не догадка о посте, а решение
    человека, и жанр поста его не меняет. Читает он весь исходный текст, а
    модели достаётся урезанный по её бюджету.
    """
    score = score_parsed(parsed, pipeline.skills_cache)
    blocked = blacklist_refusal(check_blacklist(text, pipeline.blacklist_patterns))
    logger.debug(
        "vacancy %s: score=%d threshold=%d blacklist=%s",
        vacancy_id, score, pipeline.rs.scoring_threshold, blocked,
    )
    if blocked is not None:
        return VacancyStatus.NOT_FIT, blocked, score
    refusal, unasked = await _unfit_refusal(pipeline, parsed, text, vacancy_id)
    if unasked:
        return None
    if refusal is not None:
        return VacancyStatus.NOT_FIT, refusal, score
    status, skip_reason = decide_vacancy_status(
        score, threshold=pipeline.rs.scoring_threshold
    )
    return status, skip_reason, score


async def _finish_parse(pipeline, vacancy_id: int, parsed, outcome: Outcome) -> bool:
    """Записать исход, отправить отклик, если можно, и догнать переписку.

    Догон идёт последним нарочно: пойди он раньше, вытащил бы наше же
    письмо прежде, чем отправка закоммитит свою строку, — и в переписке
    появился бы дубль без вакансии.

    Отвечает, дошла ли запись: не дошла — отклик не отправляют и человеку
    говорят «не удалось», а не «готово» над карточкой, которая не менялась.
    """
    written = await persist_parse_outcome(pipeline, vacancy_id, parsed, outcome)
    if written is None:
        return False
    hr, created = written
    await _auto_send_if_allowed(pipeline, hr, parsed, vacancy_id, outcome.status)
    if created:
        dm_backfill.spawn_hr_backfill(pipeline, hr)
    return True


async def _thrown_out_by_the_verdict(
    pipeline, vacancy_id: int, skip_reason: str | None, allow_delete: bool
) -> bool:
    """Убрать строку, если так решил приговор; сказать, убрали ли.

    Метку мусора ставит один — заслон жанра, — и значит она одно: это не
    вакансия. Зовы о пригодности такой метки не выносят: они отвечают о
    пригодности вакансии, признанной вакансией до них. Метка соискательского
    поста сюда не приходит тоже, она решает раньше и своей дорогой
    (`_thrown_out_as_a_resume`).
    """
    return bool(
        skip_reason
        and skip_reason.startswith(TRASH_SKIP_PREFIX)
        and await _dropped_as_trash(
            pipeline, vacancy_id, skip_reason, allow_delete=allow_delete
        )
    )


async def parse_and_update_vacancy(
    pipeline, vacancy_id: int, text: str, channel_username: str,
    *, allow_delete: bool = True,
) -> bool:
    """Разобрать объявление, вынести приговор и записать исход; сказать, вышло ли.

    ``allow_delete`` разводит две дороги: непригодную строку удаляют там, где
    зовущий ручается за текст приговора; прогон заново не разрешает никогда.

    «Не вышло» — спросить модель не удалось либо исход не записался; пустой
    разбор к ним не относится, это состоявшийся приговор. Различие нужно окну.

    Метка соискательского поста стоит раньше разбора: она стоит ноль.
    """
    mark = resume_mark(text[:VACANCY_TEXT_CHARS])
    if mark is not None:
        return await _thrown_out_as_a_resume(pipeline, vacancy_id, mark, allow_delete)
    parsed, refusal, stored = await _parsed_or_dropped(
        pipeline, vacancy_id, text, channel_username, allow_delete
    )
    if refusal is not None:
        return False
    if parsed is None:
        return stored
    verdict = await _verdict_for(pipeline, parsed, text, vacancy_id)
    if verdict is None:
        return False
    status, skip_reason, score = verdict
    if await _thrown_out_by_the_verdict(
        pipeline, vacancy_id, skip_reason, allow_delete
    ):
        return True
    return await _finish_parse(
        pipeline,
        vacancy_id,
        parsed,
        Outcome(
            status=status,
            skip_reason=skip_reason,
            score=score,
            keep_previous_stack=True,
        ),
    )


async def is_unparsed_vacancy(pipeline, vacancy_id: int) -> bool:
    """A vacancy is 'orphaned' when its embedding row is in the cache
    but the LLM-pipeline never finished (parser cancelled, process
    crashed, LLM call failed silently). Reads the explicit
    ``is_parsed`` flag instead of inferring from ``title is None``
    because rerun-path empty/trash rows legitimately have no title
    but ARE parsed (status=NotFit, skip_reason='empty:...').
    """
    async with pipeline.session_factory() as session:
        v = await session.get(Vacancy, vacancy_id)
    return v is not None and not v.is_parsed


async def save_empty_vacancy(
    pipeline, vacancy_id: int, parsed: ParsedVacancy | None,
    *, reason: str = EMPTY_SKIP_REASON,
) -> bool:
    """Записать непригодную строку пометкой, когда удалять её нельзя.

    Пишется то, что разбор всё же вытащил, — обычно заголовок и ещё один
    сигнал из пяти, по которым выносится приговор «пусто»: человек видит
    вакансию в окне и решает руками. Что именно записалось, считается по
    строке после записи (`_fields_filled`), а не предполагается заранее.

    Пустой разбор чистит поля. Приходит он двумя дорогами: разбора не было
    вовсе — пост опознан по метке — либо он не дал даже названия. Оставь мы
    прежние поля, окно показало бы разобранное прошлым заходом рядом с
    приговором «мусор», то есть выдало бы старое за новое.
    """
    written = await persist_parse_outcome(
        pipeline,
        vacancy_id,
        parsed,
        Outcome(
            status=VacancyStatus.NOT_FIT,
            skip_reason=reason,
            score=0,
            keep_previous_stack=False,
        ),
    )
    if written is None:
        return False
    hr, hr_created = written
    if hr_created:
        dm_backfill.spawn_hr_backfill(pipeline, hr)
    return True
