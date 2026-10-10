"""Решение отправить отклик: письмо, охраны от повтора и запись исхода."""

import logging
import time
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from adapters import telegram
from backend.applying.telegram_letter import (
    RECENT_SEND_WINDOW_DAYS,
    Letter,
    format_channel_ref,
    full_letter,
    parsed_from_row,
    short_note,
)
from backend.models import Vacancy
from backend.models import VacancyStatus
from backend.payloads import ParsedVacancy
from backend.repository.hr_identify import count_recent_outgoing_with_vacancy_for_hr

logger = logging.getLogger(__name__)

# Вакансии, отправка по которым идёт прямо сейчас. Живёт в модуле, а не в
# конвейере: отправку заводят обе дороги — кнопка окна и авто-отправка
# разбора, — а конвейер у них общий один, и держать список на нём значило бы
# только дальше идти за тем же самым. Замка не нужно: обе дороги идут на одном
# цикле asyncio, и между проверкой и записью сюда никто не вклинится.
_SENDING: set[int] = set()


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
    wait_until = pipeline.rs.flood_wait_until_ts
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
    async with pipeline.session_factory() as session:
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
                session, hr.id, window_days=RECENT_SEND_WINDOW_DAYS,
            ),
            (v.title or "").strip(),
            format_channel_ref(
                v.channel.username if v.channel is not None else None
            ),
        )


async def _hand_letter_over(
    pipeline, hr, letter: Letter, vacancy_id: int, force: bool
) -> tuple:
    """Отдать письмо отправке; отдать признак удачи и код исхода.

    Резюме может исчезнуть между проверкой и открытием файла внутри
    Pyrogram — это касается только полного письма, у короткого вложения
    нет вовсе.
    """
    try:
        sent = await pipeline.send(
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
    # Ложь от отправки значит одно из двух: заслон — чёрный список, некуда
    # писать — или отказ Telegram по частоте, после которого
    # письма нет. Что именно, сказано в её собственной записи.
    return (True, "sent") if sent else (False, "blocked")


async def _still_sendable(pipeline, vacancy_id: int, force: bool) -> str | None:
    """Не перещёлкнулся ли статус, пока готовилось письмо; отказ или пустота.

    У короткого письма ожидания модели нет, но проверка дешёвая и стоит
    одинаково на обеих дорогах: иначе ручная и автоматическая отправки
    разъезжались бы по разным сторожам.
    """
    if force:
        return None
    async with pipeline.session_factory() as session:
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

    Вторую отправку по той же вакансии, пока идёт первая, отбиваем здесь.
    Заслон «уже откликались» её не ловит: он смотрит на статус, а статус
    меняется в самом конце — после того как модель сочинит письмо. Всё это
    время нажатие в окне заводило бы вторую отправку, и HR получал бы два
    письма подряд.
    """
    if vacancy_id in _SENDING:
        logger.info("vacancy %d: send already in flight, refusing second", vacancy_id)
        return False, "in_flight"
    _SENDING.add(vacancy_id)
    try:
        return await _send_the_letter(pipeline, hr, parsed, vacancy_id, force)
    finally:
        _SENDING.discard(vacancy_id)


async def _send_the_letter(
    pipeline, hr, parsed: ParsedVacancy, vacancy_id: int, force: bool
) -> tuple[bool, str]:
    """Собрать письмо и отдать его; сказать, ушло ли и почему нет."""
    refusal, plan = await _send_plan(pipeline, hr, vacancy_id, force)
    if refusal is not None:
        return False, refusal
    if plan.prior_count == 0:
        letter, letter_refusal = await full_letter(
            pipeline, parsed, plan.channel_ref, vacancy_id
        )
        if letter is None:
            return False, letter_refusal
    else:
        letter = Letter(
            short_note(plan.title, plan.channel_ref, plan.prior_count), None
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


async def send_application_for_vacancy(pipeline, vacancy_id: int) -> tuple[bool, str]:
    """Manual cover-letter send (UI «Отправить отклик»). Reconstructs
    ParsedVacancy from the stored Vacancy row so the LLM-prompt has the
    same shape as the auto-send path. Returns (ok, reason). Reasons:
    'sent' / 'no_vacancy' / 'no_hr' / 'already_applied' / любой код
    из send_application."""
    async with pipeline.session_factory() as session:
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
        # Отказ здесь, а не ниже: `force=True` минует заслон `_send_refusal`,
        # а письмо уходит до перевода статуса — HR получил бы второе, и то,
        # что `APPLY_MOVES_FROM` потом не пустит `APPLIED → APPLIED`, уже неважно.
        # Читается то же, что в `_send_refusal`, а слово окну другое, и это
        # не повтор: там гонка с моделью, здесь человек нажал сам и должен
        # услышать, что отклик уже был.
        if v.status == VacancyStatus.APPLIED:
            logger.info(
                "send_application: vacancy %d already APPLIED, refusing re-send",
                vacancy_id,
            )
            return False, "already_applied"
        hr = v.hr
        parsed = parsed_from_row(v)
    if not pipeline.profile_block:
        await pipeline.reload_resources()
    return await send_application(pipeline, hr, parsed, vacancy_id, force=True)
