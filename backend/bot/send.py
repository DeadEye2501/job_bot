"""Доставка отклика в Telegram: вложение, ограничения сервиса, след в базе."""

import logging

from adapters import telegram
from backend.bot import can_send
from backend.models import HR
from backend.models import Message
from backend.repository.vacancies_life import add_vacancy_event
from backend.repository.vacancies_life import mark_vacancy_applied

logger = logging.getLogger(__name__)


def _applied_label(force: bool) -> str:
    """Чем подписан перевод в «отклик отправлен» в истории вакансии."""
    return "Ручная отправка." if force else "Авто-отправка отклика."


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

    Под замком отправки (`SEND_LOCKED`, тестовый режим) настоящего вызова
    Telegram нет, а всё остальное идёт как при отправке: вакансия переходит
    в «откликнулись», история статусов и лента пишутся. Строка сообщения —
    единственное исключение: её не пишут нарочно, потому что номера
    сообщения в Telegram не существует, а строка с пустым номером показала
    бы в переписке письмо, которого HR не получал.
    """
    # Заслоны те же, что у переписки из окна: одно объявление на двоих.
    permission = await can_send.can_send_to_hr(bot, hr)
    target = permission.target
    # Заглушают отправку ровно два замка, и оба названы поимённо. Причина, о
    # которой мы не знаем, — заведённая позже, и зачесть по ней отклик значило
    # бы пометить вакансию откликнутой без письма, то есть закрыть её от
    # следующей попытки навсегда. Умолчание тут — отказ.
    suppressed = permission.refusal in (can_send.DRY_RUN, can_send.SENDING_LOCKED)
    if permission.refusal is not None and not suppressed:
        logger.warning(
            "Bot.send: %s (hr=%s, адресат=%s, чёрный список=%s, vacancy=%s)",
            permission.refusal, hr.id, target,
            permission.blacklist_value, vacancy_id,
        )
        return False
    # Под замком имитируем удачную отправку: не сделав этого, конвейер
    # нельзя было бы обкатать без живых HR. Текст письма в журнал не идёт —
    # в нём имя, работодатели и навыки из анкеты; след суппрессии остаётся
    # отметкой в ленте вакансии.
    tg_msg_id: int | None = None
    if suppressed:
        logger.warning(
            "[%s] would have sent DM to %s (vacancy=%s, %d chars, attachment=%s)",
            permission.refusal, target, vacancy_id, len(text), attachment,
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
                # SEND_LOCKED-пометка раньше дописывалась в explanation —
                # но это делало запись в истории разной в dev и проде.
                # Аудит факта суппрессии живёт в
                # VacancyEvent(kind="applied_sent").payload.suppressed.
                applied_now = await mark_vacancy_applied(
                    session, vacancy_id, _applied_label(force), force=force
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
                    if await mark_vacancy_applied(
                        session, vacancy_id, _applied_label(force), force=force
                    ):
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
                await add_vacancy_event(
                    session,
                    vacancy_id,
                    "applied_sent",
                    {
                        "hr_id": hr.id,
                        "force": force,
                        "suppressed": suppressed,
                        "cover_letter_chars": len(text),
                        "tg_message_id": tg_msg_id,
                    },
                )
                await session.commit()
        except Exception:
            logger.exception(
                "applied_sent VacancyEvent persist failed",
                extra={"vacancy_id": vacancy_id},
            )
    return True
