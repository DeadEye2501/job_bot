"""Доставка отклика в Telegram: вложение, ограничения сервиса, след в базе."""

import logging

from adapters import telegram
from backend.domain.transitions import should_apply_status
from backend.models import BotMode
from backend.models import HR
from backend.models import Message
from backend.models import Vacancy
from backend.models import VacancyEvent
from backend.models import VacancyStatus
from backend.models import VacancyStatusHistory
from backend.repository.hr_card import _hr_blacklist_value

logger = logging.getLogger(__name__)


def _shares_provider(a, b) -> bool:
    """Two LLM provider configs share the same httpx client if endpoint+auth match.

    Model name is intentionally NOT compared — model is per-request, not on
    the client.
    """
    return (
        a is not None
        and b is not None
        and a.base_url == b.base_url
        and a.api_key == b.api_key
    )


async def ui_send_vacancy_application(bot, vacancy_id: int) -> tuple[bool, str]:
    """Manual cover-letter send — vacancy detail «more» menu, кнопка
    «Отправить отклик». Возвращает (ok, reason) — UI использует reason
    для понятного toast'а (что именно не сработало)."""
    logger.info("UI send application for vacancy %d", vacancy_id)
    return await bot._ingestion.send_application_for_vacancy(vacancy_id)


async def send(
    bot,
    hr: HR,
    text: str,
    attachment=None,
    vacancy_id: int | None = None,
    *,
    force: bool = False,
) -> bool:
    """DM-send для cover-letter flow. Возвращает True когда отклик
    зачтён (реально ушёл в Telegram ИЛИ заглушен SEND_LOCKED/dry_run
    — но БД-эффект состоялся). False — когда отклик НЕ должен
    считаться сделанным: hr без target, BotMode.OFF, blacklist.

    SEND_LOCKED / dry_run: реальная отправка через telegram.send_dm
    не происходит, но Message row, status=APPLIED и весь downstream
    (VacancyStatusHistory etc.) проходят как при настоящей отправке.
    Текст письма уходит в логи WARNING — для аудита/тестов.
    """
    target = hr.telegram_user_id or hr.telegram_username
    if target is None:
        logger.warning(
            "Bot.send: hr %s has no telegram_user_id or username, skipping (vacancy=%s)",
            hr.id, vacancy_id,
        )
        return False
    # OFF mode = «бот в покое». Авто-цикл туда не дойдёт (poll пропускает),
    # но manual «Отправить отклик» из UI должен тоже уважать стоп-режим.
    if (await bot._current_mode()) is BotMode.OFF:
        logger.warning(
            "Bot.send: BotMode.OFF, suppressed send to %s (vacancy=%s)",
            target, vacancy_id,
        )
        return False
    # Blacklist: HR мог попасть туда между парсингом вакансии и отправкой
    # отклика (особенно для авто-flow, где между парсингом и send'ом
    # может пройти время на LLM-генерацию). Зеркалит проверку из
    # send_to_hr_chat / send_to_hr_media.
    async with bot._session_factory() as session:
        bl_value = await _hr_blacklist_value(session, hr)
    if bl_value:
        logger.warning(
            "Bot.send: hr %s in blacklist (%s), suppressed (vacancy=%s)",
            hr.id, bl_value, vacancy_id,
        )
        return False
    # SEND_LOCKED / dry_run: имитируем успешную отправку — реального
    # вызова Pyrogram'у не делаем. Дальнейший DB-апдейт (Message row +
    # status=APPLIED) идёт как обычно — иначе тестировать pipeline без
    # реальных HR-ов нельзя. Текст письма В ЛОГ НЕ ПИШЕМ (PII: имя,
    # работодатели, скилы из profile_block); если нужен аудит сэмули-
    # рованной отправки — смотри Message-row, она пишется в БД даже в
    # suppressed-режиме.
    suppressed = bot._dry_run or telegram.SEND_LOCKED
    tg_msg_id: int | None = None
    if suppressed:
        tag = "[DRY-RUN]" if bot._dry_run else "[SEND_LOCKED]"
        logger.warning(
            "%s would have sent DM to %s (vacancy=%s, %d chars, attachment=%s)",
            tag, target, vacancy_id, len(text), attachment,
        )
    else:
        logger.info(
            "Sending DM to hr %s (vacancy=%s, %d chars)",
            target, vacancy_id, len(text),
        )
        from pyrogram.errors import FloodWait
        import time as _time
        try:
            tg_msg_id = await telegram.send_dm(
                bot._client, target, text, attachment
            )
        except FloodWait as e:
            # Persist'им «не пытайся до этого времени» в app_settings
            # — apply.try_auto_send проверит и пропустит
            # auto-send'ы пока окно не закроется. Для manual UI-send
            # это просто возврат False — юзер увидит «Telegram отказался»
            # toast и попробует позже.
            secs = int(getattr(e, "value", 0) or 0)
            until = _time.time() + secs
            logger.warning(
                "Bot.send: FloodWait %d сек, persist'у flood_wait_until_ts",
                secs,
            )
            try:
                await bot._rs.set_app(
                    "flood_wait_until_ts", str(until)
                )
            except Exception:
                logger.exception(
                    "Bot.send: failed to persist flood_wait_until_ts"
                )
            return False
    # При успешной отправке очистим flood_wait_until_ts (если он
    # был — Telegram отпустил). Не критично, но тогда try_auto_send
    # не будет проверять стэйл-окно после восстановления.
    if not suppressed and bot._rs.flood_wait_until_ts > 0:
        try:
            await bot._rs.set_app("flood_wait_until_ts", "0")
        except Exception:
            logger.exception(
                "Bot.send: failed to clear flood_wait_until_ts"
            )
    # С этого момента сообщение УШЛО к HR (или сэмулировано). Если
    # коммит ниже упадёт — сообщение в Telegram реальное, а Message-row
    # в БД нет. Чтобы повторное «Отправить отклик» НЕ отправило DM
    # ещё раз, делаем fallback-flip status=APPLIED отдельной тонкой
    # транзакцией: пусть аудит-row потерян, но re-send отбивается
    # стандартной already_applied-проверкой в send_application_for_vacancy.
    # SEND_LOCKED / dry_run: Message-row НЕ пишем (раньше писали «для
    # аудита», но получалось что in-app HR-чат показывал фантомное
    # сообщение, которого в реальном Telegram нет — юзеры путались).
    # Аудит покрыт VacancyEvent(kind="applied_sent") ниже + флагом
    # suppressed=True в его payload'е.
    try:
        async with bot._session_factory() as session:
            if not suppressed:
                session.add(
                    Message(
                        is_incoming=False,
                        hr_id=hr.id,
                        vacancy_id=vacancy_id,
                        text=text,
                        tg_message_id=tg_msg_id,
                    )
                )
            applied_now = False
            if vacancy_id is not None:
                v = await session.get(Vacancy, vacancy_id)
                if v is not None and should_apply_status(
                    v.status, VacancyStatus.APPLIED, force=force
                ):
                    previous_status = v.status
                    v.status = VacancyStatus.APPLIED
                    applied_now = True
                    # Status-history row нужен чтобы таймлайн вакансии
                    # показал «Applied: …» — без этого NEW→APPLIED-флип
                    # из Bot.send проходил молча, в UI было видно
                    # только applied_sent VacancyEvent (без статус-цвета).
                    kind_label = (
                        "Ручная отправка."
                        if force
                        else "Авто-отправка отклика."
                    )
                    # SEND_LOCKED-пометка раньше дописывалась в
                    # explanation — но это делало timeline-запись разной
                    # в dev и проде. Аудит факта суппрессии живёт в
                    # VacancyEvent(kind="applied_sent").payload.suppressed.
                    session.add(
                        VacancyStatusHistory(
                            vacancy_id=vacancy_id,
                            message_id=None,
                            previous_status=previous_status,
                            status=VacancyStatus.APPLIED,
                            explanation=kind_label,
                            applied=True,
                        )
                    )
            await session.commit()
    except Exception:
        logger.error(
            "Bot.send: DB commit FAILED after%s telegram send to %s "
            "(vacancy=%s, %d chars); message is sent but no Message row "
            "recorded. Attempting standalone status flip to block re-send.",
            " (suppressed)" if suppressed else "",
            target, vacancy_id, len(text),
            exc_info=True,
        )
        if vacancy_id is not None:
            try:
                async with bot._session_factory() as session:
                    v = await session.get(Vacancy, vacancy_id)
                    if v is not None and should_apply_status(
                        v.status, VacancyStatus.APPLIED, force=force
                    ):
                        v.status = VacancyStatus.APPLIED
                        await session.commit()
                        logger.info(
                            "vacancy %s status -> APPLIED via fallback "
                            "(audit Message-row missing)",
                            vacancy_id,
                        )
            except Exception:
                logger.exception(
                    "Bot.send: fallback status-flip also FAILED for "
                    "vacancy=%s — re-send protection broken, watch out",
                    vacancy_id,
                )
        # Возвращаем True — в Telegram сообщение реально ушло (или
        # сэмулировано в SEND_LOCKED-режиме), повторная отправка не нужна.
        return True
    if applied_now:
        logger.info("vacancy %s status -> APPLIED after send", vacancy_id)
    # Audit-event: фиксируем факт фактической отправки cover-letter'а
    # (real DM или SEND_LOCKED-имитация) — это нужно для UI-таймлайна
    # вакансии, иначе у юзера только Message-row + status flip,
    # без явной строки «отклик отправлен» в истории. force=True от
    # ручного UI выделяем отдельным флагом.
    if vacancy_id is not None:
        try:
            async with bot._session_factory() as session:
                session.add(
                    VacancyEvent(
                        vacancy_id=vacancy_id,
                        kind="applied_sent",
                        payload={
                            "hr_id": hr.id,
                            "force": force,
                            "suppressed": suppressed,
                            "cover_letter_chars": len(text),
                            "tg_message_id": tg_msg_id,
                        },
                    )
                )
                await session.commit()
        except Exception:
            logger.exception(
                "applied_sent VacancyEvent persist failed",
                extra={"vacancy_id": vacancy_id},
            )
    return True
