"""Решение отправить отклик: письмо, охраны от повтора и запись исхода."""

import logging
import time
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from adapters import telegram
from backend.llm.cover_letter import generate_cover_letter
from backend.models import Vacancy
from backend.models import VacancyStatus
from backend.payloads import DIRECT_PARSED_FIELDS, ParsedVacancy
from backend.repository.hr_identify import count_recent_outgoing_with_vacancy_for_hr

logger = logging.getLogger(__name__)


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


def _send_refusal(v, *, force: bool, when: str) -> str | None:
    """Почему отклик слать нельзя: код отказа для окна, а можно — пусто.

    Заслон спрашивают дважды — до сборки письма и после задержки на модель;
    двойная проверка задумана, а вот правило чтения одно, и разойдись оно,
    окно получало бы на одной и той же гонке разные ответы. `when` идёт
    только в журнал: по нему видно, какой из двух заслонов сработал.
    """
    if v is None:
        return "no_vacancy"
    if not force and v.status == VacancyStatus.APPLIED:
        logger.info(
            "vacancy %d: status already APPLIED %s "
            "(race with manual UI or parallel auto-flow)",
            v.id, when,
        )
        return "race"
    return None


async def try_auto_send(
    pipeline, hr, parsed: ParsedVacancy, vacancy_id: int
) -> tuple[bool, str]:
    """Wrapper над send_application с уважением FloodWait-окна.
    Возвращает тот же (ok, reason) контракт; дополнительный reason-код
    ``flood_wait``.
    """
    # FloodWait persist: Bot.send (через send_application → _send)
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

    return await send_application(pipeline, hr, parsed, vacancy_id)


@dataclass(frozen=True, slots=True)
class _Letter:
    """Письмо к отправке: текст и вложение к нему.

    Пара настоящая: у полного письма вложение есть всегда, у короткого его
    нет никогда, и решается это одним и тем же выбором ветки.
    """

    text: str
    attachment: object | None


@dataclass(frozen=True, slots=True)
class _Plan:
    """Из чего собирать письмо: сколько уже писали, о чём и откуда.

    Три значения читаются одним запросом и вместе решают вид письма:
    счёт прежних выбирает ветку, название и канал идут в текст.
    """

    prior_count: int
    title: str
    channel_ref: str | None


async def _send_plan(pipeline, hr, vacancy_id: int, force: bool) -> tuple:
    """Отказ заслона или замысел письма; вторым всегда одно из двух.

    Отказ здесь — сторож гонки: статус мог уже перещёлкнуться ручной
    отправкой или встречным потоком. Ручная отправка его перебивает —
    человек сам решил повторить.

    Счёт прежних писем этому HR за окно решает, каким будет письмо: первое
    идёт полным, следующие короткими. Это заслон от спама, когда HR
    выкладывает несколько вакансий и обход видит их одним заходом.
    """
    async with pipeline._session_factory() as session:
        v = (
            await session.scalars(
                select(Vacancy)
                .where(Vacancy.id == vacancy_id)
                .options(selectinload(Vacancy.channel))
            )
        ).first()
        refusal = _send_refusal(v, force=force, when="at send-time")
        if refusal is not None:
            return refusal, None
        return None, _Plan(
            await count_recent_outgoing_with_vacancy_for_hr(
                session, hr.id, window_days=_RECENT_SEND_WINDOW_DAYS,
            ),
            (v.title or "").strip(),
            _format_channel_ref(
                v.channel.username if v.channel is not None else None
            ),
        )


async def _full_letter(pipeline, parsed: ParsedVacancy, channel_ref: str, vacancy_id: int):
    """Полное письмо с резюме; при беде — пара «пусто и код отказа».

    Название и канал вплетает в текст сама модель: детерминированная
    приставка «Откликаюсь на вакансию: …» выглядела штампом поверх живого
    письма и потому снята.
    """
    if not pipeline._profile_block:
        logger.warning("vacancy %d: profile_block empty, skipping send", vacancy_id)
        return None, "profile_empty"
    body = await generate_cover_letter(
        pipeline._profile_block, parsed,
        pipeline._lm_client, pipeline._lm_chat_model,
        channel_ref=channel_ref,
    )
    if body is None:
        logger.warning(
            "vacancy %d: cover letter generation failed, skipping send", vacancy_id
        )
        return None, "cover_letter_failed"
    cv_path = pipeline._cv_path()
    if cv_path is None or not cv_path.is_file():
        logger.warning(
            "vacancy %d: CV file missing (%s), skipping send", vacancy_id, cv_path
        )
        return None, "cv_missing"
    return _Letter(body, cv_path), None


async def _hand_letter_over(
    pipeline, hr, letter: _Letter, vacancy_id: int, force: bool
) -> tuple:
    """Отдать письмо отправке; отдать признак удачи и код исхода.

    Резюме может исчезнуть между проверкой и открытием файла внутри
    Pyrogram — это касается только полного письма, у короткого вложения
    нет вовсе.
    """
    try:
        sent = await pipeline._send(
            hr, letter.text, attachment=letter.attachment,
            vacancy_id=vacancy_id, force=force,
        )
    except FileNotFoundError:
        logger.warning(
            "vacancy %d: CV file disappeared between check and send", vacancy_id
        )
        return False, "cv_missing"
    except Exception:
        logger.exception(
            "vacancy %d: send failed",
            vacancy_id,
            extra={"vacancy_id": vacancy_id, "hr_id": hr.id},
        )
        return False, "telegram_error"
    # Ложь от отправки значит заслон: выключенный бот, чёрный список или
    # некуда писать. Какой именно — сказано в её собственной записи.
    return (True, "sent") if sent else (False, "blocked")


async def _still_sendable(pipeline, vacancy_id: int, force: bool) -> str | None:
    """Не перещёлкнулся ли статус, пока готовилось письмо; отказ или пустота.

    У короткого письма ожидания модели нет, но проверка дешёвая и стоит
    одинаково на обеих дорогах: иначе ручная и автоматическая отправки
    разъезжались бы по разным сторожам.
    """
    if force:
        return None
    async with pipeline._session_factory() as session:
        return _send_refusal(
            await session.get(Vacancy, vacancy_id),
            force=force,
            when="during send-prep",
        )


async def send_application(
    pipeline, hr, parsed: ParsedVacancy, vacancy_id: int, *, force: bool = False,
) -> tuple[bool, str]:
    """Отправить HR отклик на вакансию; сказать, ушёл ли и почему нет.

    Первое письмо этому HR за окно идёт полным — с резюме и письмом от
    модели; следующие короткими, без вложений и без модели. Это заслон от
    спама: HR выкладывает несколько вакансий, обход видит их одним заходом.

    Код исхода читает окно и пишет по нему подсказку — иначе человек не
    отличит отправку от молчаливого пропуска. Пустое название отправку не
    отменяет: в шаблоне оно вырождается в «вашу вакансию».
    """
    refusal, plan = await _send_plan(pipeline, hr, vacancy_id, force)
    if refusal is not None:
        return False, refusal
    if plan.prior_count == 0:
        letter, letter_refusal = await _full_letter(
            pipeline, parsed, plan.channel_ref, vacancy_id
        )
        if letter is None:
            return False, letter_refusal
    else:
        letter = _Letter(
            _build_short_text(plan.title, plan.channel_ref, plan.prior_count), None
        )
    refusal = await _still_sendable(pipeline, vacancy_id, force)
    if refusal is not None:
        return False, refusal
    ok, reason = await _hand_letter_over(pipeline, hr, letter, vacancy_id, force)
    if not ok:
        return False, reason
    logger.info(
        "vacancy %d: %s %s to hr %d (prior_count=%d)",
        vacancy_id,
        "short follow-up" if plan.prior_count else "cover letter",
        "simulated (SEND_LOCKED)" if telegram.SEND_LOCKED else "sent",
        hr.id, plan.prior_count,
    )
    return True, "sent"


def _parsed_from_row(v: Vacancy) -> ParsedVacancy:
    """Собрать разобранную вакансию обратно из строки базы.

    Наставлению модели нужен тот же вид, что и на самотёке, иначе письмо
    вручную сочинялось бы по другим данным. Прямые поля берутся перечнем
    `DIRECT_PARSED_FIELDS` — тем же, каким разбор их и записывал: со своим
    списком новое поле до ручного отклика не доехало бы молча.

    Остальное собирается здесь: пустое название вакансии становится пустой
    строкой (у разобранной оно не пустует), сайт компании и второй контакт в
    строке не хранятся вовсе, а стек хранится одним списком — в обязательный
    он и уходит: занизить требование хуже, чем завысить.
    """
    direct = {name: getattr(v, name) for name in DIRECT_PARSED_FIELDS}
    return ParsedVacancy(
        **{**direct, "title": v.title or ""},
        company_website=None,
        other_contact=None,
        stack_required=list(v.stack or []),
        stack_preferred=[],
    )


async def send_application_for_vacancy(pipeline, vacancy_id: int) -> tuple[bool, str]:
    """Manual cover-letter send (UI «Отправить отклик»). Reconstructs
    ParsedVacancy from the stored Vacancy row so the LLM-prompt has the
    same shape as the auto-send path. Returns (ok, reason). Reasons:
    'sent' / 'no_vacancy' / 'no_hr' / 'already_applied' / любой код
    из send_application."""
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
        parsed = _parsed_from_row(v)
    if not pipeline._profile_block:
        await pipeline._reload_resources()
    return await send_application(pipeline, hr, parsed, vacancy_id, force=True)
