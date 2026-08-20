"""Приговор объявлению: разбор моделью, вердикт по разобранному и что дальше.

Всё здесь про одно — чем объявление кончилось: спросить модель, свериться с
чёрным списком, вынести приговор, выбросить мусор, отправить отклик пригодному,
пометить пустышку. Куда исход ложится, знает сосед (`flows/parse_write`);
зовут его отсюда, а не наоборот.
"""

import logging

from backend.flows import dm_backfill
from backend.domain.blacklist import check_blacklist
from backend.domain.scoring import score_parsed
from backend.domain.verdict import decide_vacancy_status
from backend.domain.verdict import is_empty_vacancy
from backend.domain.verdict import (
    EMPTY_SKIP_REASON,
    LLM_SKIP_PREFIX,
    TRASH_SKIP_PREFIX,
    TRUNCATED_SKIP_REASON,
)
from backend.llm.answers import TRUNCATED_TROUBLE
from backend.llm.fit import validate_vacancy_fit
from backend.llm.vacancy import parse_vacancy
from backend.models import Vacancy
from backend.payloads import ParsedVacancy
from backend.models import VacancyStatus
from backend.flows.events import record_vacancy_event

from backend.flows import apply
from backend.flows import cleanup
from backend.flows.parse_write import Outcome, persist_parse_outcome

logger = logging.getLogger(__name__)


async def _dropped_as_trash(
    pipeline, vacancy_id: int, reason: str, *, allow_delete: bool
) -> bool:
    """Убрать непригодную вакансию, если убирать разрешено; сказать, убрали ли.

    Приговор «непригодна» выносят дважды — пустышке и вердикту «мусор», — и
    развилка у него одна. Разрешение приходит доводом от зовущего: приём поста
    даёт его целому тексту (пост оказался не вакансией, и держать его незачем)
    и не даёт недобравшему — в таком одна шапка со ссылкой, и разбору видна
    пустышка. Прогон заново не разрешает никогда: строку человек открыл
    руками, и исчезнуть у него из-под курсора она не должна; непригодность
    остаётся пометкой в причине отказа.
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


async def _fit_refusal(
    pipeline, parsed, text: str, vacancy_id: int
) -> tuple[str | None, bool]:
    """Причина, по которой модель отвергла вакансию, и «спросить не вышло».

    Пустая причина значит «годится». Второе значение отделяет от неё беду
    провайдера: по ней приговора нет вовсе, и строку нельзя помечать
    разобранной — лежащий полчаса провайдер иначе уводит в «не подходит» всё,
    что пришло за это время, а вернуть их можно только кнопкой по каждой.

    Неразобранный ответ считается отказом нарочно: закрытая дверь тут
    дешевле открытой — человек пересмотрит вакансию руками, а вот отклик,
    ушедший по невнятному вердикту, не отзовёшь. Причина с меткой мусора
    отличается от прочих тем, что по ней строку можно убрать вовсе; решает
    это зовущий.
    """
    validation, trouble = await validate_vacancy_fit(
        parsed,
        text,
        pipeline.lm_client,
        pipeline.lm_chat_model,
        profile=pipeline.profile_cache,
    )
    logger.debug(
        "vacancy %s: fit verdict=%s reason=%r",
        vacancy_id,
        validation.verdict if validation else None,
        validation.reason if validation else None,
    )
    if trouble == TRUNCATED_TROUBLE:
        logger.warning(
            "vacancy %s: вердикт не поместился даже с запасом, отдаю человеку",
            vacancy_id,
        )
        return TRUNCATED_SKIP_REASON, False
    if trouble is not None:
        logger.warning(
            "vacancy %s: вердикт не спросился (%s), оставляю неразобранной",
            vacancy_id, trouble,
        )
        return None, True
    if validation is None:
        logger.warning(
            "validate_vacancy_fit unavailable for vacancy parse, marking Not Fit"
        )
        return f"{LLM_SKIP_PREFIX}validation unavailable", False
    if validation.verdict == "trash":
        return f"{TRASH_SKIP_PREFIX}{validation.reason or 'no reason'}", False
    if validation.verdict == "reject":
        return f"{LLM_SKIP_PREFIX}{validation.reason or 'rejected'}", False
    return None, False


async def _auto_send_if_allowed(
    pipeline, hr, parsed, vacancy_id: int, status: VacancyStatus
) -> None:
    """Отправить отклик, если можно; попытку записать при любом исходе.

    Запись нужна затем, что через месяцы человек смотрит на новую вакансию
    с опознанным HR и пройденным порогом и не понимает, почему отклик так
    и не ушёл. Без строки в ленте ответа на это нет нигде.
    """
    if status != VacancyStatus.NEW or hr is None or not pipeline.rs.auto_apply:
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
    сверх названия, то есть это мем, обрывок или рекламная строчка, и второе
    обращение к модели ей не положено. Дальше две дороги — удалить или
    пометить, — и выбор между ними держит `_dropped_as_trash`.

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
    if refusal == TRUNCATED_TROUBLE:
        logger.warning(
            "vacancy %s: ответ не поместился даже с запасом, отдаю человеку",
            vacancy_id,
        )
        return None, None, await save_empty_vacancy(
            pipeline, vacancy_id, None, reason=TRUNCATED_SKIP_REASON
        )
    if refusal is not None:
        logger.warning("vacancy %s: разбор не состоялся (%s)", vacancy_id, refusal)
        return None, refusal, False
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

    Чёрный список читает весь исходный текст: разбору он достаётся урезанным
    по бюджету модели, и образец за обрезом всё равно ловится. Оценщика
    спрашивают только у тех, кого не отсеяли раньше, — второе обращение к
    модели стоит денег.
    """
    blacklist_match = check_blacklist(text, pipeline.blacklist_patterns)
    score = score_parsed(parsed, pipeline.skills_cache)
    logger.debug(
        "vacancy %s: score=%d threshold=%d blacklist=%s",
        vacancy_id, score, pipeline.rs.scoring_threshold, blacklist_match,
    )
    status, skip_reason = decide_vacancy_status(
        parsed, score, blacklist_match, threshold=pipeline.rs.scoring_threshold,
    )
    if status == VacancyStatus.NEW:
        refusal, unasked = await _fit_refusal(pipeline, parsed, text, vacancy_id)
        if unasked:
            return None
        if refusal is not None:
            status, skip_reason = VacancyStatus.NOT_FIT, refusal
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
    """Убрать строку, если так решил вердикт модели; сказать, убрали ли.

    Метку мусора ставит только вердикт (`_fit_refusal`), и она же —
    единственный повод убрать строку. Кто заведёт её с другой стороны, тот и
    отвечает за удаление.
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

    ``allow_delete`` разводит две дороги: непригодную строку удаляют только
    там, где зовущий за неё ручается, — приём поста разрешает это целому
    тексту и запрещает недобравшему, — а прогон заново не разрешает никогда,
    потому что строку открыл человек. Умолчание истинно только ради приёма.

    «Не вышло» значит одно из двух: спросить модель не удалось или исход не
    записался. Пустой разбор — это состоявшийся приговор, и он истина.
    Различие нужно окну: на отказе оно говорит «не удалось перезапустить»
    вместо «готово» над карточкой, которая не менялась.
    """
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
    """Persist an empty/trash vacancy as Not Fit when auto-delete is off
    (rerun path). Fills whatever fields LLM did extract — заголовок и, как
    правило, ещё один сигнал из пяти, по которым выносится приговор
    «пусто», — so the user can see the vacancy in the UI and decide what
    to do manually. Что именно записалось, считается по строке после
    записи (`_fields_filled`), а не предполагается заранее.

    When ``parsed is None`` (LLM failed to even extract a title — e.g.
    rerun on a stale row that was previously parsed but now triggers an
    LLM error) the stored fields are cleared. Otherwise the UI would
    show the previous parse output alongside skip_reason="empty",
    which is misleading.
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
