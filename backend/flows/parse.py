"""Разбор объявления с приговором и записью."""

import logging
from dataclasses import dataclass

from backend.flows import dm_backfill
from backend.domain.blacklist import check_blacklist
from backend.domain.salary import parse_salary
from backend.domain.scoring import score_parsed
from backend.domain.verdict import decide_vacancy_status
from backend.domain.verdict import is_empty_vacancy
from backend.domain.verdict import (
    EMPTY_SKIP_REASON,
    LLM_SKIP_PREFIX,
    TRASH_SKIP_PREFIX,
)
from backend.telegram_lookup import fetch_telegram_avatar
from backend.telegram_lookup import resolve_hr_telegram
from backend.llm.fit import validate_vacancy_fit
from backend.llm.vacancy import parse_vacancy
from backend.models import HR
from backend.models import Vacancy
from backend.models import VacancyStatus
from backend.payloads import DIRECT_PARSED_FIELDS, ParsedVacancy
from backend.repository.companies_matching import find_or_create_company
from backend.repository.hr_identify import find_or_create_hr
from backend.flows.events import record_vacancy_event
from backend.repository.vacancies_life import add_vacancy_event

from backend.flows import apply
from backend.flows import cleanup

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _Outcome:
    """Чем кончился разбор объявления и что из этого следует для записи.

    ``keep_previous_stack`` разводит две ветки. У обычного разбора пустой
    стек означает осечку модели, и прежние теги вместе с прежней оценкой
    перезапись переживают. У пустышки он означает сам приговор, и в
    строку идёт то, что пришло.
    """

    status: VacancyStatus
    skip_reason: str | None
    score: int
    keep_previous_stack: bool


async def _dropped_as_trash(
    pipeline, vacancy_id: int, reason: str, *, allow_delete: bool
) -> bool:
    """Убрать непригодную вакансию, если убирать разрешено; сказать, убрали ли.

    Приговор «непригодна» выносят дважды — пустышке и вердикту «мусор», — и
    развилка у него одна. При обычном разборе строку удаляют: пост оказался
    не вакансией, и держать его незачем. При повторном разборе не удаляют
    вовсе — строку человек открыл руками, и исчезнуть у него из-под курсора
    она не должна; непригодность остаётся пометкой в причине отказа. Разойдись
    развилка, одна из двух дорог удаляла бы там, где человек этого не просил.
    """
    if not allow_delete:
        logger.info(
            "vacancy %s: %s, marking Not Fit (rerun, no auto-delete)",
            vacancy_id, reason,
        )
        return False
    logger.info("vacancy %s: %s, deleting as trash", vacancy_id, reason)
    await cleanup.delete_vacancy_as_trash(pipeline, vacancy_id, reason=reason)
    return True


async def _fit_refusal(pipeline, parsed, text: str, vacancy_id: int) -> str | None:
    """Причина, по которой модель отвергла вакансию; пустота — годится.

    Неразобранный ответ считается отказом нарочно: закрытая дверь тут
    дешевле открытой — человек пересмотрит вакансию руками, а вот отклик,
    ушедший по невнятному вердикту, не отзовёшь. Причина с меткой мусора
    отличается от прочих тем, что по ней строку можно убрать вовсе; решает
    это зовущий.
    """
    validation = await validate_vacancy_fit(
        parsed,
        text,
        pipeline._lm_client,
        pipeline._lm_chat_model,
        profile=pipeline._profile_cache,
        known_skills=pipeline._skills_cache,
    )
    logger.debug(
        "vacancy %s: fit verdict=%s reason=%r",
        vacancy_id,
        validation.verdict if validation else None,
        validation.reason if validation else None,
    )
    if validation is None:
        logger.warning(
            "validate_vacancy_fit unavailable for vacancy parse, marking Not Fit"
        )
        return f"{LLM_SKIP_PREFIX}validation unavailable"
    if validation.verdict == "trash":
        return f"{TRASH_SKIP_PREFIX}{validation.reason or 'no reason'}"
    if validation.verdict == "reject":
        return f"{LLM_SKIP_PREFIX}{validation.reason or 'rejected'}"
    return None


async def _auto_send_if_allowed(
    pipeline, hr, parsed, vacancy_id: int, status: VacancyStatus
) -> None:
    """Отправить отклик, если можно; попытку записать при любом исходе.

    Запись нужна затем, что через месяцы человек смотрит на новую вакансию
    с опознанным HR и пройденным порогом и не понимает, почему отклик так
    и не ушёл. Без строки в ленте ответа на это нет нигде.
    """
    if status != VacancyStatus.NEW or hr is None or not pipeline._rs.auto_apply:
        return
    ok, reason = await apply.try_auto_send(pipeline, hr, parsed, vacancy_id)
    await record_vacancy_event(
        pipeline._session_factory,
        vacancy_id,
        "auto_send",
        {"ok": ok, "reason": reason},
    )


async def _parsed_or_dropped(
    pipeline, vacancy_id: int, text: str, channel_username: str, allow_delete: bool
):
    """Разобрать объявление; пустота в ответ — с ним уже покончено.

    Пустышку отсеиваем до модели-оценщика: разбор не вытащил ни одного поля
    сверх названия, то есть это мем, обрывок или рекламная строчка, и второе
    обращение к модели ей не положено. Дальше две дороги — удалить или
    пометить, — и выбор между ними держит `_dropped_as_trash`.
    """
    parsed = await parse_vacancy(
        text,
        pipeline._lm_client,
        pipeline._lm_chat_model,
        channel_username=channel_username,
        known_skills=pipeline._skills_cache,
    )
    if not is_empty_vacancy(parsed):
        return parsed
    if not await _dropped_as_trash(
        pipeline, vacancy_id, EMPTY_SKIP_REASON, allow_delete=allow_delete
    ):
        await save_empty_vacancy(pipeline, vacancy_id, parsed)
    return None


async def _verdict_for(pipeline, parsed, text: str, vacancy_id: int) -> tuple:
    """Приговор объявлению: статус, причина отказа и баллы.

    Чёрный список читает весь исходный текст: разбору он достаётся урезанным
    по бюджету модели, и образец за обрезом всё равно ловится. Оценщика
    спрашивают только у тех, кого не отсеяли раньше, — второе обращение к
    модели стоит денег.
    """
    blacklist_match = check_blacklist(text, pipeline._blacklist_patterns)
    score = score_parsed(parsed, pipeline._skills_cache)
    logger.debug(
        "vacancy %s: score=%d threshold=%d blacklist=%s",
        vacancy_id, score, pipeline._rs.scoring_threshold, blacklist_match,
    )
    status, skip_reason = decide_vacancy_status(
        parsed, score, blacklist_match, threshold=pipeline._rs.scoring_threshold,
    )
    if status == VacancyStatus.NEW:
        refusal = await _fit_refusal(pipeline, parsed, text, vacancy_id)
        if refusal is not None:
            status, skip_reason = VacancyStatus.NOT_FIT, refusal
    return status, skip_reason, score


async def _finish_parse(pipeline, vacancy_id: int, parsed, outcome: _Outcome) -> None:
    """Записать исход, отправить отклик, если можно, и догнать переписку.

    Догон идёт последним нарочно: пойди он раньше, вытащил бы наше же
    письмо прежде, чем отправка закоммитит свою строку, — и в переписке
    появился бы дубль без вакансии.
    """
    hr, created = await _persist_parse_outcome(pipeline, vacancy_id, parsed, outcome)
    await _auto_send_if_allowed(pipeline, hr, parsed, vacancy_id, outcome.status)
    if created:
        dm_backfill.spawn_hr_backfill(pipeline, hr)


async def parse_and_update_vacancy(
    pipeline, vacancy_id: int, text: str, channel_username: str,
    *, allow_delete: bool = True,
) -> None:
    """Разобрать объявление, вынести приговор и записать исход.

    ``allow_delete`` разводит две дороги: при обычном обходе непригодную
    строку удаляют, при повторном разборе — никогда, потому что её открыл
    человек. Умолчание истинно только ради обхода.
    """
    parsed = await _parsed_or_dropped(
        pipeline, vacancy_id, text, channel_username, allow_delete
    )
    if parsed is None:
        return
    status, skip_reason, score = await _verdict_for(
        pipeline, parsed, text, vacancy_id
    )
    if (
        skip_reason
        and skip_reason.startswith(TRASH_SKIP_PREFIX)
        and await _dropped_as_trash(
            pipeline, vacancy_id, skip_reason, allow_delete=allow_delete
        )
    ):
        return
    await _finish_parse(
        pipeline,
        vacancy_id,
        parsed,
        _Outcome(
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
    async with pipeline._session_factory() as session:
        v = await session.get(Vacancy, vacancy_id)
    return v is not None and not v.is_parsed


async def _resolve_hr(pipeline, parsed: ParsedVacancy | None):
    """Разыскать HR в Telegram и забрать заодно его аватар.

    Идёт до открытия сессии: иначе SQLite ждал бы ответа сети в
    незакоммиченном состоянии.
    """
    if parsed is None or not parsed.hr_contact:
        return None, None
    user = await resolve_hr_telegram(pipeline._client, parsed.hr_contact)
    if user is None:
        return None, None
    return user, await fetch_telegram_avatar(pipeline._client, user)


def _clear_parsed_fields(v: Vacancy, score: int) -> None:
    """Стереть прошлый разбор: колонки в пусто, стек — пустым списком.

    Оценка приходит доводом, а не нулём по месту: «разобрать не вышло» —
    тоже исход разбора, и число ему назначает тот, кто исход вынес.
    """
    for name in DIRECT_PARSED_FIELDS:
        setattr(v, name, None)
    v.stack = []
    v.score = score
    v.salary_min = None
    v.salary_max = None
    v.salary_currency = None
    v.notes = None


def _apply_parsed_fields(
    v: Vacancy, parsed: ParsedVacancy | None, outcome: _Outcome
) -> None:
    """Перенести разобранное в строку вакансии.

    Разбора нет вовсе — прежние поля стираются: иначе в карточке рядом с
    причиной «пусто» висел бы прошлый разбор, и это читалось бы как
    поломка приложения.
    """
    if parsed is None:
        _clear_parsed_fields(v, outcome.score)
        return
    for name in DIRECT_PARSED_FIELDS:
        setattr(v, name, getattr(parsed, name))
    if parsed.stack or not outcome.keep_previous_stack:
        v.stack = parsed.stack
        v.score = outcome.score
    else:
        # Стек и оценка держатся парой: оценка считается от стека, и
        # записав пустой стек с нулевой оценкой, карточка показала бы
        # ноль баллов рядом с прежними тегами.
        v.stack = v.stack or []
        if v.score is None:
            v.score = outcome.score
    v.salary_min, v.salary_max, v.salary_currency = parse_salary(parsed.salary)
    v.notes = (
        f"Контакты: {parsed.other_contact}" if parsed.other_contact else None
    )


def _fields_filled(v: Vacancy) -> list[str]:
    """Чем строка вакансии после записи заполнена — это уходит в ленту.

    Стек в общий перечень не входит — он не переносится из разбора, а
    пересчитывается вместе с оценкой, — но встаёт сразу за контактом HR, а не
    в хвост: порядок здесь не оформление, а часть уже записанных строк ленты,
    и перестановка развела бы новые строки со старыми молча.
    """
    names = list(DIRECT_PARSED_FIELDS)
    names.insert(names.index("hr_contact") + 1, "stack")
    return [name for name in names if getattr(v, name)]


async def _write_parsed_row(
    session, vacancy_id: int, parsed: ParsedVacancy | None, outcome: _Outcome
) -> Vacancy | None:
    """Записать исход разбора в саму строку вакансии; отдать её или пустоту.

    Пустота означает «строки больше нет»: пользователь мог удалить её из
    окна, пока шёл разбор. Отвечать на это исключением нечем — исход уже
    вынесен, писать его некуда, и работа на этом кончается.

    Признак «разобрано» ставится здесь же, в той же транзакции, что и поля:
    упади запись между ними, строка осталась бы помеченной разобранной с
    полями от прошлого раза.
    """
    v = await session.get(Vacancy, vacancy_id)
    if v is None:
        return None
    v.status = outcome.status
    v.skip_reason = outcome.skip_reason
    v.is_parsed = True
    _apply_parsed_fields(v, parsed, outcome)
    return v


async def _link_company(session, v: Vacancy, parsed, pipeline) -> dict | None:
    """Привязать компанию по имени из разбора; отдать решение о сведении.

    Решение отдаётся наружу затем, что уходит в ленту: сведение компаний
    спрашивает языковую модель, и по чему именно она решила, разбирают
    потом по строке ленты, а не по журналу.

    Компания привязывается и у непригодной вакансии — как и собеседник:
    ссылки из карточки в «Компании» и «HR» должны работать одинаково у
    любой строки, иначе имя компании в карточке есть, а перехода на неё
    нет.
    """
    if parsed is None or not parsed.company_name:
        return None
    company, decision = await find_or_create_company(
        session,
        parsed.company_name,
        website=parsed.company_website,
        lm_client=pipeline._lm_client,
        lm_model=pipeline._lm_chat_model,
    )
    if company is not None:
        v.company_id = company.id
    return decision


async def _link_resolved_hr(session, v: Vacancy, resolved) -> tuple[HR | None, bool]:
    """Привязать разысканного собеседника; отдать его и признак «только заведён».

    Признак нужен зовущему, а не здесь: по нему решается, догонять ли
    переписку, и догон обязан идти уже после закрытия сессии.
    """
    user, avatar = resolved
    if user is None:
        return None, False
    hr, created = await find_or_create_hr(session, user, avatar=avatar)
    v.hr_id = hr.id
    return hr, created


def _parsed_event_payload(v: Vacancy, outcome: _Outcome, decision) -> dict:
    """Что уходит в ленту строкой «разобрано».

    Решение о сведении компании кладётся только когда оно было: пустое
    поле в ленте читалось бы как «сводили и не свели».
    """
    payload: dict = {
        "score": outcome.score,
        "status": outcome.status.value,
        "fields_filled": _fields_filled(v),
        "skip_reason": outcome.skip_reason,
    }
    if decision is not None:
        payload["company_dedup"] = decision
    return payload


async def _persist_parse_outcome(
    pipeline, vacancy_id: int, parsed: ParsedVacancy | None, outcome: _Outcome
) -> tuple[HR | None, bool]:
    """Провести исход разбора через сессию: розыск, запись, оповещение окна.

    Сама запись разложена по трём объявлениям выше — строка, компания,
    собеседник; здесь остаётся чужое им: сессия, поломка посреди записи и
    оповещение окна после. Розыск идёт первым и стоит двух сетевых
    обращений — это самая медленная и ломкая часть работы, и в сессии ей
    не место (см. `_resolve_hr`).

    Отдаёт HR и признак «только что заведён»: отклик пустышке не положен,
    а догон переписки обязан идти и после закрытия сессии, и после
    отправки отклика — иначе он вытащит наше же письмо раньше, чем оно
    запишется. Вне сессии HR пригоден: ``expire_on_commit=False``.
    """
    resolved = await _resolve_hr(pipeline, parsed)
    hr, hr_created = None, False
    async with pipeline._session_factory() as session:
        try:
            v = await _write_parsed_row(session, vacancy_id, parsed, outcome)
            if v is None:
                return None, False
            decision = await _link_company(session, v, parsed, pipeline)
            hr, hr_created = await _link_resolved_hr(session, v, resolved)
            await add_vacancy_event(
                session, vacancy_id, "parsed",
                _parsed_event_payload(v, outcome, decision),
            )
            await session.commit()
        except Exception:
            logger.exception(
                "vacancy %s: parse persist failed", vacancy_id,
                extra={"vacancy_id": vacancy_id},
            )
            return None, False

    pipeline._fire_contacts_changed()
    pipeline._fire_vacancies_changed()
    return hr, hr_created


async def save_empty_vacancy(
    pipeline, vacancy_id: int, parsed: ParsedVacancy | None
) -> None:
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
    hr, hr_created = await _persist_parse_outcome(
        pipeline,
        vacancy_id,
        parsed,
        _Outcome(
            status=VacancyStatus.NOT_FIT,
            skip_reason=EMPTY_SKIP_REASON,
            score=0,
            keep_previous_stack=False,
        ),
    )
    if hr_created:
        dm_backfill.spawn_hr_backfill(pipeline, hr)
