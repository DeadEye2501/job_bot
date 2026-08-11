"""Разбор объявления с приговором и записью."""

import logging
from dataclasses import dataclass

from backend.flows import dm_backfill
from backend.domain.blacklist import check_blacklist
from backend.domain.salary import parse_salary
from backend.domain.scoring import score_parsed
from backend.domain.verdict import decide_vacancy_status
from backend.domain.verdict import is_empty_vacancy
from backend.domain.verdict import EMPTY_SKIP_REASON, TRASH_SKIP_PREFIX
from backend.helpers import fetch_telegram_avatar
from backend.helpers import resolve_hr_telegram
from backend.llm.fit import validate_vacancy_fit
from backend.llm.vacancy import parse_vacancy
from backend.models import HR
from backend.models import Vacancy
from backend.models import VacancyStatus
from backend.payloads import ParsedVacancy
from backend.repository.companies_matching import find_or_create_company
from backend.repository.hr_identify import find_or_create_hr
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


async def parse_and_update_vacancy(
    pipeline,
    vacancy_id: int,
    text: str,
    channel_username: str,
    *,
    allow_delete: bool = True,
) -> None:
    """Parse + classify + persist for a vacancy.

    ``allow_delete=True`` preserves the historical auto-ingest behavior
    (trash verdict → row gone) and is the default only for backwards
    compatibility with that path. **New callers should normally pass
    ``False``** — silent deletion under a user-initiated action is
    almost always the wrong UX, and bulk channel ingest is the only
    place where it makes sense.
    """
    parsed = await parse_vacancy(
        text,
        pipeline._lm_client,
        pipeline._lm_chat_model,
        channel_username=channel_username,
        known_skills=pipeline._skills_cache,
    )

    # Раннее отсеивание пустышек: если LLM вообще не извлек структуру
    # (parsed=None) или извлек только title без любых других полезных
    # полей — это мусорный пост (мем, обрывок, рекламная строчка).
    # Не тратим токены на LLM-валидатор и не оставляем в Not Fit:
    # либо удаляем (auto-ingest), либо помечаем явным skip_reason
    # для ручного просмотра (rerun).
    if is_empty_vacancy(parsed):
        if allow_delete:
            logger.info(
                "vacancy %s: empty vacancy (no meaningful fields), deleting as trash",
                vacancy_id,
            )
            await cleanup.delete_vacancy_as_trash(pipeline,
                vacancy_id, reason=EMPTY_SKIP_REASON
            )
            return
        logger.info(
            "vacancy %s: empty vacancy (no meaningful fields), marking Not Fit (rerun, no auto-delete)",
            vacancy_id,
        )
        await save_empty_vacancy(pipeline, vacancy_id, parsed)
        return

    # blacklist scans the FULL raw text; parse_vacancy truncates to 6000
    # chars due to LLM token budget — patterns past the cutoff still apply
    blacklist_match = check_blacklist(text, pipeline._blacklist_patterns)
    # Score is computed over LLM-extracted required/preferred stack
    # (already canonicalized via {KNOWN_SKILLS_BLOCK}, deduped, capitalized).
    # required: +level / -1, preferred: +(level-1) / 0. See score_parsed.
    # ``parsed`` is guaranteed non-None here: ``is_empty_vacancy(None)`` is
    # True and we'd have returned above. ``assert`` is purely for type
    # narrowing.
    assert parsed is not None
    score = score_parsed(parsed, pipeline._skills_cache)
    logger.debug(
        "vacancy %s: score=%d threshold=%d blacklist=%s",
        vacancy_id,
        score,
        pipeline._rs.scoring_threshold,
        blacklist_match,
    )
    status, skip_reason = decide_vacancy_status(
        parsed, score, blacklist_match,
        threshold=pipeline._rs.scoring_threshold,
    )

    if status == VacancyStatus.NEW:
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
        # fail-closed: missing/unparseable validation routes to Not Fit
        # so the user can re-evaluate manually rather than auto-applying
        if validation is None:
            status = VacancyStatus.NOT_FIT
            skip_reason = "llm: validation unavailable"
            logger.warning(
                "validate_vacancy_fit unavailable for vacancy parse, marking Not Fit"
            )
        elif validation.verdict == "trash":
            if allow_delete:
                logger.info(
                    "vacancy %s: classified as trash by LLM (%s), deleting",
                    vacancy_id, validation.reason or "no reason",
                )
                await cleanup.delete_vacancy_as_trash(pipeline, 
                    vacancy_id,
                    reason=f"{TRASH_SKIP_PREFIX}{validation.reason or 'no reason'}",
                )
                return
            logger.info(
                "vacancy %s: trash verdict, marking Not Fit (rerun, no auto-delete)",
                vacancy_id,
            )
            status = VacancyStatus.NOT_FIT
            skip_reason = f"{TRASH_SKIP_PREFIX}{validation.reason or 'no reason'}"
        elif validation.verdict == "reject":
            status = VacancyStatus.NOT_FIT
            skip_reason = f"llm: {validation.reason or 'rejected'}"

    hr_for_send, hr_created = await _persist_parse_outcome(
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

    # Авто-отправка отклика: вакансия прошла score-threshold + LLM-fit-
    # validator (status остался NEW), HR резолвлен в Telegram-юзера,
    # юзер не выключил auto_apply, лимиты не превышены — генерируем
    # cover letter и отправляем с прикреплённым CV.
    if (
        status == VacancyStatus.NEW
        and hr_for_send is not None
        and pipeline._rs.auto_apply
    ):
        ok, reason = await apply.try_auto_send(pipeline, 
            hr_for_send, parsed, vacancy_id
        )
        # Audit-event: фиксируем КАЖДУЮ попытку auto-send'а вне
        # зависимости от исхода — иначе юзер смотрит на NEW-вакансию
        # через месяцы и не может понять «почему авто-отправка не
        # сработала, ведь HR резолвлен и score прошёл».
        try:
            async with pipeline._session_factory() as session:
                await add_vacancy_event(
                    session,
                    vacancy_id,
                    "auto_send",
                    {"ok": ok, "reason": reason},
                )
                await session.commit()
        except Exception:
            logger.exception(
                "auto_send event persist failed",
                extra={"vacancy_id": vacancy_id},
            )

    # ПОСЛЕ auto-send'а: иначе backfill может через get_chat_history
    # вытащить cover-letter сообщение раньше, чем Bot.send закоммитит
    # свою row с vacancy_id'ом — и вставит дубль без vacancy_id, а
    # Bot.send'овский insert упадёт на UNIQUE.
    if hr_created:
        dm_backfill.spawn_hr_backfill(pipeline, hr_for_send)


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
    v.title = None
    v.description = None
    v.company_name = None
    v.hr_contact = None
    v.stack = []
    v.score = score
    v.grade = None
    v.salary = None
    v.salary_min = None
    v.salary_max = None
    v.salary_currency = None
    v.remote = None
    v.location = None
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
    v.title = parsed.title
    v.description = parsed.description
    v.company_name = parsed.company_name
    v.hr_contact = parsed.hr_contact
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
    v.grade = parsed.grade
    v.salary = parsed.salary
    v.salary_min, v.salary_max, v.salary_currency = parse_salary(parsed.salary)
    v.remote = parsed.remote
    v.location = parsed.location
    v.notes = (
        f"Контакты: {parsed.other_contact}" if parsed.other_contact else None
    )


def _fields_filled(v: Vacancy) -> list[str]:
    """Чем строка вакансии после записи заполнена — это уходит в ленту."""
    return [
        name for name, val in (
            ("title", v.title),
            ("description", v.description),
            ("company_name", v.company_name),
            ("hr_contact", v.hr_contact),
            ("stack", v.stack),
            ("grade", v.grade),
            ("salary", v.salary),
            ("remote", v.remote),
            ("location", v.location),
        ) if val
    ]


async def _persist_parse_outcome(
    pipeline, vacancy_id: int, parsed: ParsedVacancy | None, outcome: _Outcome
) -> tuple[HR | None, bool]:
    """Разыскать HR в Telegram и записать исход разбора: поля, компанию,
    HR и запись в ленту.

    Розыск идёт первым и стоит двух сетевых обращений — это самая
    медленная и самая ломкая часть работы, и она здесь именно потому,
    что в сессии ей не место (см. `_resolve_hr`).

    Отдаёт привязанного HR и признак того, что строка HR только что
    заведена. Наружу они уходят потому, что здесь их деть некуда:
    отклик пустышке не положен вовсе, а догон переписки обязан идти и
    после закрытия сессии, и после отправки отклика — иначе он вытащит
    наше же письмо раньше, чем оно запишется. HR остаётся пригодным за
    пределами сессии: ``session_factory`` собран с
    ``expire_on_commit=False``.

    Компания и HR привязываются и у непригодной вакансии: ссылки из
    карточки в «Компании» и «HR» должны работать одинаково у любой
    строки, иначе имя компании в карточке есть, а перехода на неё нет.
    """
    resolved_hr_user, resolved_hr_avatar = await _resolve_hr(pipeline, parsed)
    hr: HR | None = None
    hr_created = False
    async with pipeline._session_factory() as session:
        try:
            v = await session.get(Vacancy, vacancy_id)
            if v is None:
                return None, False

            v.status = outcome.status
            v.skip_reason = outcome.skip_reason
            # Marks the row as fully populated by the LLM pipeline —
            # see ``Vacancy.is_parsed`` docstring. Set inside the same
            # transaction as the parsed fields so a crash after this
            # point still leaves the row consistent.
            v.is_parsed = True
            _apply_parsed_fields(v, parsed, outcome)

            company_dedup_decision: dict | None = None
            if parsed is not None and parsed.company_name:
                company, company_dedup_decision = await find_or_create_company(
                    session,
                    parsed.company_name,
                    website=parsed.company_website,
                    lm_client=pipeline._lm_client,
                    lm_model=pipeline._lm_chat_model,
                )
                if company is not None:
                    v.company_id = company.id

            if resolved_hr_user is not None:
                hr, hr_created = await find_or_create_hr(
                    session, resolved_hr_user, avatar=resolved_hr_avatar
                )
                v.hr_id = hr.id

            event_payload: dict = {
                "score": outcome.score,
                "status": outcome.status.value,
                "fields_filled": _fields_filled(v),
                "skip_reason": outcome.skip_reason,
            }
            if company_dedup_decision is not None:
                event_payload["company_dedup"] = company_dedup_decision
            await add_vacancy_event(
                session,
                vacancy_id,
                "parsed",
                event_payload,
            )
            await session.commit()
        except Exception:
            logger.exception(
                "vacancy %s: parse persist failed",
                vacancy_id,
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
