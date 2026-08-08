"""Отправка отклика на вакансию."""

import logging
import time

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from adapters import telegram
from backend.llm.candidate import CandidateLanguage
from backend.llm.candidate import CandidateProfile
from backend.llm.cover_letter import generate_cover_letter
from backend.models import Profile
from backend.models import ProfileLanguage
from backend.models import Vacancy
from backend.models import VacancyStatus
from backend.payloads import ParsedVacancy
from backend.repository.hr_identify import count_recent_outgoing_with_vacancy_for_hr

logger = logging.getLogger(__name__)


def _build_candidate_profile(
    profile: Profile | None,
    languages: list[ProfileLanguage],
) -> CandidateProfile:
    """Собирает срез данных профиля для LLM-валидатора. Если профиль ещё не
    создан — возвращает пустой CandidateProfile (валидатор подставит '—' и
    относится к этому как «нет ограничений»)."""
    if profile is None:
        return CandidateProfile()
    return CandidateProfile(
        title=profile.title,
        location=profile.location,
        grades=list(profile.grades or []),
        work_formats=list(profile.work_format or []),
        languages=[
            CandidateLanguage(name=l.language, level=l.level) for l in languages
        ],
        free_preferences=profile.free_preferences,
    )


# ---------------------------------------------------------------- send-templates
# Окно «недавно отправляли cover letter этому HR'у» (см.
# count_recent_outgoing_with_vacancy_for_hr). Старше — шлём полный
# cover letter + CV, как первый раз.
_RECENT_SEND_WINDOW_DAYS = 14


def _format_channel_ref(channel_username: str | None) -> str | None:
    """Нормализуем @-handle для подстановки в шаблоны. None → None
    (caller дропает строку «Канал: …» целиком, чтобы не рендерилось
    «Канал: None»)."""
    if not channel_username:
        return None
    s = channel_username.strip()
    if not s:
        return None
    return s if s.startswith("@") else f"@{s}"


def _build_short_text(
    title: str, channel_ref: str | None, prior_count: int,
) -> str:
    """Hardcoded follow-up. ``prior_count`` — сколько раз мы уже писали
    этому HR'у cover letter в окне (1 → «А вот ещё одну», 2+ → «И ещё
    одну»). Пустой title не блокирует — деградируемся в обобщённое
    «вашу вакансию» (отправить отклик важнее, чем точно подписать)."""
    if title:
        intro = (
            f"А вот я увидел ещё одну интересную вакансию: {title}"
            if prior_count == 1
            else f"И ещё одну: {title}"
        )
    else:
        intro = (
            "А вот я увидел ещё одну вашу вакансию"
            if prior_count == 1
            else "И ещё одну вашу вакансию"
        )
    if channel_ref:
        intro += f"\nКанал: {channel_ref}"
    return intro


async def _try_auto_send(
    pipeline, hr, parsed: ParsedVacancy, vacancy_id: int
) -> tuple[bool, str]:
    """Wrapper над _send_application с уважением FloodWait-окна.
    Возвращает тот же (ok, reason) контракт; дополнительный reason-код
    ``flood_wait``.
    """
    # FloodWait persist: Bot.send (через _send_application → _send)
    # на FloodWait выписывает в app_settings момент когда можно
    # пробовать снова. Дёргать send_dm раньше — гарантированный
    # повторный FloodWait и накопление штрафа.
    wait_until = pipeline._rs.flood_wait_until_ts
    if wait_until > 0:
        remaining = wait_until - time.time()
        if remaining > 0:
            logger.warning(
                "vacancy %d: skipping auto-send, FloodWait еще %d сек",
                vacancy_id, int(remaining),
            )
            return False, "flood_wait"

    return await _send_application(pipeline, hr, parsed, vacancy_id)


async def _send_application(
    pipeline,
    hr,
    parsed: ParsedVacancy,
    vacancy_id: int,
    *,
    force: bool = False,
) -> tuple[bool, str]:
    """Send cover letter (или short follow-up) HR'у для vacancy_id.

    Решение «полный cover letter + CV» vs «короткий follow-up без
    вложений» принимается по count'у наших исходящих этому HR'у с
    привязанным vacancy_id за последние ``_RECENT_SEND_WINDOW_DAYS``
    дней (см. ``count_recent_outgoing_with_vacancy_for_hr``). 0 →
    полный, ≥1 → short. Это анти-спам гард на случай, когда HR
    публикует несколько вакансий и pipeline видит их в одном цикле:
    первый отклик идёт нормально, последующие — короткие «А вот ещё
    одну: …», без повторного резюме и без LLM-задержки.

    Возвращает (ok, reason). reason — короткий код:
    ``sent`` (отправка зачтена — реальный DM или SEND_LOCKED-имитация),
    ``no_vacancy`` (vacancy_id не найден), ``profile_empty`` /
    ``cover_letter_failed`` / ``cv_missing`` (только в полной ветке —
    short вариант их избегает конструктивно), ``race`` (статус успел
    флипнуться в APPLIED), ``blocked`` (OFF mode / blacklist / нет
    таргета), ``telegram_error``. Пустой title не блокирует отправку
    — деградируемся на нейтральное «вашу вакансию» в шаблоне
    (``_build_full_text`` / ``_build_short_text``).
    UI пишет toast по этому коду — иначе юзер не отличит реальную
    отправку от молчаливого skip'а.
    """
    # Загрузка вакансии + канала и подсчёт prior outgoing'ов в одной
    # сессии. Race-guard upfront: статус мог уже флипнуться (manual UI
    # или параллельный auto-flow). force=True (manual UI «Отправить
    # отклик») перебивает: юзер сам решил повторить отправку.
    async with pipeline._session_factory() as session:
        v = (
            await session.scalars(
                select(Vacancy)
                .where(Vacancy.id == vacancy_id)
                .options(selectinload(Vacancy.channel))
            )
        ).first()
        if v is None:
            return False, "no_vacancy"
        if not force and v.status == VacancyStatus.APPLIED:
            logger.info(
                "vacancy %d: status already APPLIED at send-time "
                "(race with manual UI or parallel auto-flow)",
                vacancy_id,
            )
            return False, "race"
        prior_count = await count_recent_outgoing_with_vacancy_for_hr(
            session, hr.id, window_days=_RECENT_SEND_WINDOW_DAYS,
        )
        title = (v.title or "").strip()
        channel_ref = _format_channel_ref(
            v.channel.username if v.channel is not None else None
        )

    if prior_count == 0:
        # 1-й контакт за окно — полный cover letter + CV.
        if not pipeline._profile_block:
            logger.warning(
                "vacancy %d: profile_block empty, skipping send",
                vacancy_id,
            )
            return False, "profile_empty"
        body = await generate_cover_letter(
            pipeline._profile_block, parsed,
            pipeline._lm_client, pipeline._lm_chat_model,
            channel_ref=channel_ref,
        )
        if body is None:
            logger.warning(
                "vacancy %d: cover letter generation failed, skipping send",
                vacancy_id,
            )
            return False, "cover_letter_failed"
        cv_path = pipeline._cv_path()
        if cv_path is None or not cv_path.is_file():
            logger.warning(
                "vacancy %d: CV file missing (%s), skipping send",
                vacancy_id, cv_path,
            )
            return False, "cv_missing"
        # Title и @канал теперь вплетены LLM'ом прямо в body —
        # детерминированный префикс «Откликаюсь на вакансию: …\nКанал:
        # …\n\n» убран, выглядел как штамп поверх живого письма.
        text = body
        attachment = cv_path
    else:
        # 2-й и далее в окне — hardcoded short без LLM, без CV.
        text = _build_short_text(title, channel_ref, prior_count)
        attachment = None

    # Race-guard re-check после LLM-задержки. Для short-ветки задержки
    # нет, но re-check дешёвый — оставляем симметрично, чтобы не было
    # асимметричных гонок при одновременном auto+manual.
    if not force:
        async with pipeline._session_factory() as session:
            v = await session.get(Vacancy, vacancy_id)
            if v is None:
                return False, "no_vacancy"
            if v.status == VacancyStatus.APPLIED:
                logger.info(
                    "vacancy %d: status flipped to APPLIED during "
                    "send-prep (race with manual UI or parallel auto-flow)",
                    vacancy_id,
                )
                return False, "race"
    try:
        sent = await pipeline._send(
            hr, text, attachment=attachment, vacancy_id=vacancy_id,
            force=force,
        )
    except FileNotFoundError:
        # CV-файл удалён/перемещён между is_file()-чеком выше и open'ом
        # внутри Pyrogram'а. Касается только полной ветки (short без
        # attachment'а — туда мы FileNotFoundError не доедет).
        logger.warning(
            "vacancy %d: CV file disappeared between check and send",
            vacancy_id,
        )
        return False, "cv_missing"
    except Exception:
        logger.exception(
            "vacancy %d: send failed",
            vacancy_id,
            extra={"vacancy_id": vacancy_id, "hr_id": hr.id},
        )
        return False, "telegram_error"
    if not sent:
        # Bot.send вернул False — заблочило на стадии guards (OFF mode /
        # blacklist / нет таргета). Конкретная причина в логах warning'а
        # из Bot.send.
        return False, "blocked"
    # SEND_LOCKED-факт суппрессии остаётся в логах и в
    # VacancyEvent("applied_sent").payload.suppressed; в timeline-записи
    # и в reason-коде мы его НЕ различаем.
    logger.info(
        "vacancy %d: %s %s to hr %d (prior_count=%d)",
        vacancy_id,
        "short follow-up" if prior_count else "cover letter",
        "simulated (SEND_LOCKED)" if telegram.SEND_LOCKED else "sent",
        hr.id, prior_count,
    )
    return True, "sent"


async def send_application_for_vacancy(pipeline, vacancy_id: int) -> tuple[bool, str]:
    """Manual cover-letter send (UI «Отправить отклик»). Reconstructs
    ParsedVacancy from the stored Vacancy row so the LLM-prompt has the
    same shape as the auto-send path. Returns (ok, reason). Reasons:
    'sent' / 'no_vacancy' / 'no_hr' / 'already_applied' / любой код
    из _send_application."""
    async with pipeline._session_factory() as session:
        v = (
            await session.scalars(
                select(Vacancy)
                .where(Vacancy.id == vacancy_id)
                .options(selectinload(Vacancy.hr))
            )
        ).first()
        if v is None:
            logger.warning("send_application: vacancy %d missing", vacancy_id)
            return False, "no_vacancy"
        if v.hr is None:
            logger.warning(
                "send_application: vacancy %d has no HR linked", vacancy_id
            )
            return False, "no_hr"
        # Защита от повторной отправки: если статус уже APPLIED, юзер
        # уже отправлял этот отклик. force=True ниже всё равно пройдёт
        # через should_apply_status, но Bot.send уже SEND_DM'ит ДО
        # status-flip'а, что приводит к реальному двойному сообщению
        # тому же HR. Лучше отказать в UI с понятной причиной.
        if v.status == VacancyStatus.APPLIED:
            logger.info(
                "send_application: vacancy %d already APPLIED, refusing re-send",
                vacancy_id,
            )
            return False, "already_applied"
        hr = v.hr
        parsed = ParsedVacancy(
            title=v.title or "",
            description=v.description,
            company_name=v.company_name,
            company_website=None,
            hr_contact=v.hr_contact,
            other_contact=None,
            stack_required=list(v.stack or []),
            stack_preferred=[],
            grade=v.grade,
            salary=v.salary,
            remote=v.remote,
            location=v.location,
        )
    if not pipeline._profile_block:
        await pipeline._reload_resources()
    return await _send_application(pipeline, hr, parsed, vacancy_id, force=True)
