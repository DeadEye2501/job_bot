"""Разбор объявления с приговором и записью."""

import logging

from backend.flows import dm
from backend.domain.blacklist import check_blacklist
from backend.domain.salary import normalize_salary_to_rub_thousands
from backend.domain.scoring import score_parsed
from backend.domain.verdict import decide_vacancy_status
from backend.domain.verdict import is_empty_vacancy
from backend.helpers import fetch_telegram_avatar
from backend.helpers import resolve_hr_telegram
from backend.llm.fit import validate_vacancy_fit
from backend.llm.vacancy import parse_vacancy
from backend.models import Vacancy
from backend.models import VacancyEvent
from backend.models import VacancyStatus
from backend.payloads import ParsedVacancy
from backend.repository.companies_matching import find_or_create_company
from backend.repository.hr_identify import find_or_create_hr

from backend.flows import apply
from backend.flows import cleanup

logger = logging.getLogger(__name__)


async def _parse_and_update_vacancy(
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
            await cleanup._delete_vacancy_as_trash(pipeline, 
                vacancy_id, reason="empty: no meaningful fields"
            )
            return
        logger.info(
            "vacancy %s: empty vacancy (no meaningful fields), marking Not Fit (rerun, no auto-delete)",
            vacancy_id,
        )
        await _save_empty_vacancy(pipeline, vacancy_id, parsed)
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
                await cleanup._delete_vacancy_as_trash(pipeline, 
                    vacancy_id,
                    reason=f"trash: {validation.reason or 'no reason'}",
                )
                return
            logger.info(
                "vacancy %s: trash verdict, marking Not Fit (rerun, no auto-delete)",
                vacancy_id,
            )
            status = VacancyStatus.NOT_FIT
            skip_reason = f"trash: {validation.reason or 'no reason'}"
        elif validation.verdict == "reject":
            status = VacancyStatus.NOT_FIT
            skip_reason = f"llm: {validation.reason or 'rejected'}"

    # ``parsed`` is guaranteed non-None below — see the ``assert`` upstream
    # right after the ``is_empty_vacancy`` early-return.
    # ``hr_for_send`` hoisted ВЫШЕ session-блока: оно читается на строке
    # с авто-отправкой (`if status == ... and hr_for_send is not None`)
    # ПОСЛЕ выхода из ``async with session``. Сегодня ветка ``except`` в
    # session-блоке делает ``return`` до этой проверки, поэтому код
    # корректен — но любой будущий рефакторинг (например, finally вместо
    # except-return) превратит чтение в ``UnboundLocalError``. Один
    # источник истины здесь убирает риск.
    resolved_hr_user = None
    resolved_hr_avatar = None
    hr_for_send = None
    hr_for_backfill = None
    if parsed.hr_contact:
        resolved_hr_user = await resolve_hr_telegram(
            pipeline._client, parsed.hr_contact
        )
        if resolved_hr_user is not None:
            resolved_hr_avatar = await fetch_telegram_avatar(
                pipeline._client, resolved_hr_user
            )

    async with pipeline._session_factory() as session:
        try:
            v = await session.get(Vacancy, vacancy_id)
            if v is None:
                return

            v.status = status
            v.skip_reason = skip_reason
            # Marks the row as fully populated by the LLM pipeline —
            # see ``Vacancy.is_parsed`` docstring. Set inside the same
            # transaction as the parsed fields so a crash after this
            # point still leaves the row consistent.
            v.is_parsed = True

            v.title = parsed.title
            v.description = parsed.description
            v.company_name = parsed.company_name
            v.hr_contact = parsed.hr_contact
            # Если повторный парс вернул пустой stack (LLM-регрессия —
            # модель в этот раз не извлекла скиллы), сохраняем прежний
            # stack ВМЕСТЕ со старым score. Score считается от
            # parsed.stack_required/preferred, и при пустом stack он
            # уходит в 0 — UI получал бы Python-чип при Score:0,
            # рассинхрон. Держим пару (stack, score) синхронной.
            if parsed.stack:
                v.stack = parsed.stack
                v.score = score
            else:
                v.stack = v.stack or []
                if v.score is None:
                    v.score = score
            v.grade = parsed.grade
            v.salary = parsed.salary
            v.salary_rub_min, v.salary_rub_max = (
                normalize_salary_to_rub_thousands(
                    parsed.salary,
                    usd_rate=pipeline._rs.salary_usd_to_rub,
                    eur_rate=pipeline._rs.salary_eur_to_rub,
                )
            )
            v.remote = parsed.remote
            v.location = parsed.location
            v.notes = (
                f"Контакты: {parsed.other_contact}"
                if parsed.other_contact
                else None
            )

            # Company/HR resolved even on Not Fit — keeps forensic data
            # so the user can reclassify manually in DBeaver later.
            company_dedup_decision: dict | None = None
            if parsed.company_name:
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
                # Захватываем до выхода из сессии — нужно после commit
                # для авто-отправки. session_factory с
                # expire_on_commit=False, поэтому атрибуты hr остаются
                # валидными после close.
                hr_for_send = hr
                hr_for_backfill = hr if hr_created else None

            fields_filled = [
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
            event_payload: dict = {
                "score": score,
                "status": status.value,
                "fields_filled": fields_filled,
                "skip_reason": skip_reason,
            }
            if company_dedup_decision is not None:
                event_payload["company_dedup"] = company_dedup_decision
            session.add(
                VacancyEvent(
                    vacancy_id=vacancy_id,
                    kind="parsed",
                    payload=event_payload,
                )
            )
            await session.commit()
        except Exception:
            logger.exception(
                "vacancy %s: parse update failed",
                vacancy_id,
                extra={"vacancy_id": vacancy_id},
            )
            return

    pipeline._fire_contacts_changed()
    pipeline._fire_vacancies_changed()

    # Авто-отправка отклика: вакансия прошла score-threshold + LLM-fit-
    # validator (status остался NEW), HR резолвлен в Telegram-юзера,
    # юзер не выключил auto_apply, лимиты не превышены — генерируем
    # cover letter и отправляем с прикреплённым CV.
    if (
        status == VacancyStatus.NEW
        and hr_for_send is not None
        and pipeline._rs.auto_apply
    ):
        ok, reason = await apply._try_auto_send(pipeline, 
            hr_for_send, parsed, vacancy_id
        )
        # Audit-event: фиксируем КАЖДУЮ попытку auto-send'а вне
        # зависимости от исхода — иначе юзер смотрит на NEW-вакансию
        # через месяцы и не может понять «почему авто-отправка не
        # сработала, ведь HR резолвлен и score прошёл».
        try:
            async with pipeline._session_factory() as session:
                session.add(
                    VacancyEvent(
                        vacancy_id=vacancy_id,
                        kind="auto_send",
                        payload={"ok": ok, "reason": reason},
                    )
                )
                await session.commit()
        except Exception:
            logger.exception(
                "auto_send VacancyEvent persist failed",
                extra={"vacancy_id": vacancy_id},
            )

    # ПОСЛЕ auto-send'а: иначе backfill может через get_chat_history
    # вытащить cover-letter сообщение раньше, чем Bot.send закоммитит
    # свою row с vacancy_id'ом — и вставит дубль без vacancy_id, а
    # Bot.send'овский insert упадёт на UNIQUE.
    if hr_for_backfill is not None:
        dm._spawn_hr_backfill(pipeline, hr_for_backfill)


async def _is_unparsed_vacancy(pipeline, vacancy_id: int) -> bool:
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


async def _save_empty_vacancy(
    pipeline, vacancy_id: int, parsed: ParsedVacancy | None
) -> None:
    """Persist an empty/trash vacancy as Not Fit when auto-delete is off
    (rerun path). Fills whatever fields LLM did extract (just title in
    the typical case) so the user can see the vacancy in the UI and
    decide what to do manually.

    When ``parsed is None`` (LLM failed to even extract a title — e.g.
    rerun on a stale row that was previously parsed but now triggers an
    LLM error) we explicitly clear the stored fields. Otherwise the UI
    would show the previous parse output alongside skip_reason="empty",
    which is misleading.

    Company / HR резолвятся даже здесь — тот же контракт, что в основной
    ветке: `v.company_id` / `v.hr_id` проставляются, чтобы UI мог
    нормально перейти на «Контакты / Компании» и «Контакты / HR» по
    ссылкам в детали вакансии. Без этого Not Fit-вакансии висели в БД с
    company_name строкой, но без company_id, и фронту приходилось
    отдельно вытаскивать их через picker.
    """
    # I/O: резолв HR через Telegram должен идти до открытия сессии,
    # чтобы не держать SQLite в незакоммиченном состоянии на время
    # сетевого вызова.
    resolved_hr_user = None
    resolved_hr_avatar = None
    hr_for_backfill = None
    if parsed is not None and parsed.hr_contact:
        resolved_hr_user = await resolve_hr_telegram(
            pipeline._client, parsed.hr_contact
        )
        if resolved_hr_user is not None:
            resolved_hr_avatar = await fetch_telegram_avatar(
                pipeline._client, resolved_hr_user
            )
    async with pipeline._session_factory() as session:
        try:
            v = await session.get(Vacancy, vacancy_id)
            if v is None:
                return
            v.status = VacancyStatus.NOT_FIT
            v.skip_reason = "empty: no meaningful fields"
            v.score = 0
            # Even though the row is empty/trash, the LLM pipeline did
            # run end-to-end on it — flagging it parsed lets the UI
            # show it (rerun path) and prevents the orphan-recovery
            # pass from re-parsing it forever.
            v.is_parsed = True
            company_dedup_decision: dict | None = None
            if parsed is not None:
                v.title = parsed.title
                v.description = parsed.description
                v.company_name = parsed.company_name
                v.hr_contact = parsed.hr_contact
                v.stack = parsed.stack
                v.grade = parsed.grade
                v.salary = parsed.salary
                v.salary_rub_min, v.salary_rub_max = (
                    normalize_salary_to_rub_thousands(
                    parsed.salary,
                    usd_rate=pipeline._rs.salary_usd_to_rub,
                    eur_rate=pipeline._rs.salary_eur_to_rub,
                )
                )
                v.remote = parsed.remote
                v.location = parsed.location
                v.notes = (
                    f"Контакты: {parsed.other_contact}"
                    if parsed.other_contact
                    else None
                )
                if parsed.company_name:
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
                    if hr_created:
                        hr_for_backfill = hr
            else:
                v.title = None
                v.description = None
                v.company_name = None
                v.hr_contact = None
                v.stack = []
                v.grade = None
                v.salary = None
                v.salary_rub_min = None
                v.salary_rub_max = None
                v.remote = None
                v.location = None
                v.notes = None
            event_payload: dict = {
                "score": 0,
                "status": VacancyStatus.NOT_FIT.value,
                "fields_filled": (
                    ["title"] if parsed is not None and parsed.title else []
                ),
                "skip_reason": "empty: no meaningful fields",
            }
            if company_dedup_decision is not None:
                event_payload["company_dedup"] = company_dedup_decision
            session.add(
                VacancyEvent(
                    vacancy_id=vacancy_id,
                    kind="parsed",
                    payload=event_payload,
                )
            )
            await session.commit()
            pipeline._fire_contacts_changed()
            pipeline._fire_vacancies_changed()
        except Exception:
            logger.exception(
                "vacancy %s: empty-save failed",
                vacancy_id,
                extra={"vacancy_id": vacancy_id},
            )
            return
    if hr_for_backfill is not None:
        dm._spawn_hr_backfill(pipeline, hr_for_backfill)
