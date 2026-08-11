"""Личная переписка с HR: запись сообщения в обе стороны, привязка, разбор."""

import logging

from typing import Literal

from sqlalchemy.exc import IntegrityError

from backend.bot.media import classify_media, download_media
from backend.flows.auto_gate import status_open_for_auto
from backend.helpers import extract_dm_text
from backend.helpers import extract_text
from backend.helpers import fetch_telegram_avatar
from backend.flows.dm_classify import classify_and_apply
from backend.payloads import OutgoingMessage
from backend.repository.hr_identify import find_known_hr
from backend.repository.hr_identify import find_latest_vacancy_id_for_hr
from backend.repository.hr_identify import refresh_hr_from_telegram
from backend.repository.hr_identify import resolve_reply_target_vacancy
from backend.repository.messages import find_outgoing_message
from backend.repository.messages import save_incoming_message
from backend.repository.messages import save_outgoing_message

logger = logging.getLogger(__name__)

OutgoingDmOutcome = Literal["stored", "already_stored", "not_stored"]


async def persist_outgoing_dm(session_factory, client, msg, hr_id: int) -> OutgoingDmOutcome:
    """Записать наше исходящее из Telegram; сказать, чем дело кончилось.

    Своё сообщение прилетает и эхом от Telegram, и хвостом при догоне
    переписки, а строку о нём мог завести ещё и сам отправитель. Поэтому
    исходов три, и зовущие разбирают их по-своему: «записали впервые»,
    «строка уже лежала» и «записать не вышло».

    **Проверка «уже лежит» стоит до скачивания вложения нарочно.** Путь в
    кэше собран из номера сообщения, то есть повторная загрузка целится в
    тот же файл, который в это время может читать окно, и оставляет его
    рваным — `download_media` гонится с `shutil.copy2` за один путь.
    """
    async with session_factory() as session:
        if await find_outgoing_message(session, hr_id, msg.id) is not None:
            return "already_stored"
    media_kind, media_name = classify_media(msg)
    media_path = (
        await download_media(client, msg, hr_id) if media_kind is not None else None
    )
    async with session_factory() as session:
        try:
            _, saved = await save_outgoing_message(
                session,
                OutgoingMessage(
                    hr_id=hr_id,
                    text=extract_dm_text(msg),
                    tg_message_id=msg.id,
                    sent_at=msg.date,
                    media_kind=media_kind,
                    media_path=media_path,
                    media_name=media_name,
                ),
            )
            if not saved:
                logger.debug(
                    "Outgoing DM dedup: hr=%d tg_msg=%d already saved",
                    hr_id, msg.id,
                )
                return "not_stored"
            await session.commit()
        except Exception:
            logger.exception(
                "outgoing DM persistence failed",
                extra={"hr_id": hr_id, "tg_message_id": msg.id},
            )
            return "not_stored"
    return "stored"


async def process_dm(
    msg,
    lm_client,
    lm_chat_model,
    session_factory,
    *,
    client=None,
    schedule_classification=None,
) -> None:
    if not msg.from_user or msg.from_user.is_bot:
        return
    sender_id = msg.from_user.id
    sender_username = msg.from_user.username
    # ``text`` идёт в БД (в чат-ленту) с reply-quote prefix'ом «↪…».
    # ``classify_text`` идёт в LLM-классификатор — без quote'а, чтобы
    # классификатор не оценивал как реплику HR то, что мы сами же
    # цитируем (cover-letter intro, бывшая реплика HR'а и т.п.).
    text = extract_dm_text(msg)
    classify_text = extract_text(msg)
    logger.debug(
        "DM received: sender_id=%s username=%s len=%d",
        sender_id,
        sender_username,
        len(text or ""),
    )

    # Identify HR up-front so we know where to download media to.
    async with session_factory() as session:
        hr_lookup = await find_known_hr(session, sender_id, sender_username)
        if hr_lookup is not None:
            from backend.repository.hr_card import _hr_blacklist_value
            bl_value = await _hr_blacklist_value(session, hr_lookup)
        else:
            bl_value = None
    if hr_lookup is None:
        return
    if bl_value:
        # HR в активном blacklist — игнорим входящее: не пишем в БД, не
        # классифицируем, не апдейтим статус вакансии. Тем самым переписка
        # с заблеклистенным HR полностью «глохнет» в обе стороны (исходящее
        # блочит ``send_to_hr_chat`` / ``send_to_hr_media``).
        logger.info(
            "DM from blacklisted HR ignored",
            extra={
                "hr_id": hr_lookup.id,
                "blacklist_value": bl_value,
                "tg_message_id": msg.id,
            },
        )
        return

    media_kind, media_name, media_path = None, None, None
    if client is not None:
        media_kind, media_name = classify_media(msg)
        if media_kind is not None:
            media_path = await download_media(client, msg, hr_lookup.id)

    avatar_bytes = None
    if client is not None and hr_lookup.avatar is None:
        avatar_bytes = await fetch_telegram_avatar(client, msg.from_user)

    async with session_factory() as session:
        try:
            hr = await find_known_hr(session, sender_id, sender_username)
            if hr is None:
                return
            refresh_hr_from_telegram(hr, msg.from_user, avatar=avatar_bytes)
            # Reply-attribution: если HR ответил на наше конкретное
            # сообщение через Telegram-reply, мы точно знаем, на какую
            # вакансию это реакция (наша outgoing-row в Message с этим
            # tg_message_id хранит её vacancy_id). Иначе fallback на
            # «самая свежая вакансия HR'а» — это правильное приближение
            # для одиночных HR-ов, но для multi-vacancy HR'а может
            # ошибиться (HR пишет про вторую из пяти, бот атрибутирует
            # на пятую). Reply-цепочка эту проблему как раз и решает.
            vacancy_id = None
            reply_to_id = getattr(msg, "reply_to_message_id", None)
            if reply_to_id:
                vacancy_id = await resolve_reply_target_vacancy(
                    session, hr.id, reply_to_id,
                )
            if vacancy_id is None:
                vacancy_id = await find_latest_vacancy_id_for_hr(
                    session, hr.id, as_of=msg.date,
                )
            new_msg = await save_incoming_message(
                session, hr.id, vacancy_id, text, msg.id, msg.date,
                media_kind=media_kind,
                media_path=media_path,
                media_name=media_name,
            )
            await session.commit()
            new_msg_id = new_msg.id
        except IntegrityError:
            # Duplicate (live MessageHandler racing with catch_up, or two
            # catch_ups overlapping). The row is already in the DB —
            # classification was applied on the first pass. Debug-only so
            # ops can grep if duplicates start appearing systematically.
            logger.debug(
                "DM duplicate skipped",
                extra={"sender_id": sender_id, "tg_message_id": msg.id},
            )
            return
        except Exception:
            logger.exception(
                "DM persistence failed",
                extra={"sender_id": sender_id, "tg_message_id": msg.id},
            )
            return

    if vacancy_id is None:
        return

    # Сообщение уже сохранено выше — это аудит-след входящего DM, и его
    # достаточно: разбора терминальная вакансия не получит, а призрачной
    # строки в vacancy_status_history не появится.
    is_open, v_status = await status_open_for_auto(session_factory, vacancy_id)
    if not is_open:
        logger.info(
            "vacancy %s: status=%s terminal for auto, skip classification",
            vacancy_id, v_status.value,
        )
        return

    # С debounce-планировщиком (production-путь) — сообщение в буфере,
    # классификация отложена. Без планировщика (тесты / fallback) —
    # классифицируем inline как раньше. В обоих случаях идёт
    # ``classify_text`` (без reply-quote prefix'а), не ``text``.
    if schedule_classification is not None:
        schedule_classification(hr.id, vacancy_id, new_msg_id, classify_text)
        return

    await classify_and_apply(
        session_factory,
        lm_client,
        lm_chat_model,
        classify_text,
        (vacancy_id, new_msg_id, v_status),
    )
