"""Переписка с HR из окна: отправка текста, файла и отметка о прочтении."""

import logging
import shutil

from pathlib import Path
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from adapters import telegram
from backend.models import BotMode
from backend.models import HR
from backend.models import Message
from backend.repository.hr_card import _hr_blacklist_value

from backend.bot import media

logger = logging.getLogger(__name__)


async def mark_hr_chat_read(bot, hr_id: int) -> int:
    """Mark all incoming HR messages as read in the DB AND in Telegram.

    OFF mode short-circuits: nothing is written, nothing is pinged.
    Returns the number of DB rows updated. The Pyrogram call propagates
    the read receipt to the user's other clients (phone, desktop). When
    the HR has no telegram_user_id we still update the DB but skip the
    Pyrogram side — the Telegram-side read receipt will arrive later
    through ``UpdateReadHistoryInbox`` when the user opens it elsewhere.
    """
    if (await bot._current_mode()) is BotMode.OFF:
        return 0
    from sqlalchemy import update as _sa_update
    from datetime import datetime as _dt, timezone as _tz
    now = _dt.now(_tz.utc)
    async with bot._session_factory() as session:
        hr = await session.get(HR, hr_id)
        if hr is None:
            return 0
        target = hr.telegram_user_id or hr.telegram_username
        res = await session.execute(
            _sa_update(Message)
            .where(
                Message.hr_id == hr_id,
                Message.is_incoming,
                Message.read_at.is_(None),
            )
            .values(read_at=now)
        )
        await session.commit()
        updated = res.rowcount or 0

    if updated > 0 and target is not None:
        try:
            await bot._client.read_chat_history(target)
        except Exception:
            logger.exception(
                "read_chat_history failed for hr %d", hr_id,
                extra={"hr_id": hr_id},
            )
    if updated > 0:
        logger.debug("Marked %d msgs read for hr %d", updated, hr_id)
    return updated


async def send_to_hr_chat(bot, hr_id: int, text: str) -> Message:
    """Send a chat message to an HR from the Contacts/HR pane (slice 5).

    Resolves the Telegram target as ``telegram_user_id`` (preferred —
    works even if the HR's username changed) with ``telegram_username``
    as fallback. Returns the persisted Message row.

    Raises ``RuntimeError`` for any failure mode the UI can usefully
    surface (DRY-RUN / SEND_LOCKED suppression, missing HR, missing
    Telegram contact, Pyrogram errors). Bridge converts the message
    into a toast.
    """
    if (await bot._current_mode()) is BotMode.OFF:
        raise RuntimeError("Бот выключен. Включите DM Only или Full.")
    if bot._dry_run:
        raise RuntimeError("Отправка отключена: тестовый режим.")
    if telegram.SEND_LOCKED:
        raise RuntimeError("Отправка отключена: защита от случайной отправки.")

    clean = (text or "").strip()
    if not clean:
        raise RuntimeError("Пустое сообщение.")

    async with bot._session_factory() as session:
        hr = await session.get(HR, hr_id)
        if hr is None:
            raise RuntimeError(f"HR id={hr_id} не найден.")
        target = hr.telegram_user_id or hr.telegram_username
        bl_value = await _hr_blacklist_value(session, hr)
    if target is None:
        raise RuntimeError(
            "У HR нет ни telegram_user_id, ни @username — нечем отправить."
        )
    if bl_value:
        raise RuntimeError(
            f"HR в blacklist ({bl_value}). Сначала уберите из blacklist."
        )

    pyro_msg = await bot._client.send_message(target, clean)
    logger.info(
        "Chat DM sent to hr %d (tg_msg=%d, %d chars)",
        hr_id, pyro_msg.id, len(clean),
    )

    # updates.on_dm_outgoing dispatches on the same client and may win the race —
    # it'll persist the row first and our INSERT then trips the
    # (hr_id, tg_message_id, is_incoming=False) UNIQUE. Treat that as
    # success and return the existing row.
    async with bot._session_factory() as session:
        row = Message(
            is_incoming=False,
            hr_id=hr_id,
            text=clean,
            tg_message_id=pyro_msg.id,
            sent_at=pyro_msg.date,
        )
        session.add(row)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            row = (
                await session.scalars(
                    select(Message).where(
                        Message.hr_id == hr_id,
                        Message.tg_message_id == pyro_msg.id,
                        Message.is_incoming.is_(False),
                    )
                )
            ).first()
            if row is None:
                raise
            return row
    return row


async def send_to_hr_media(bot, hr_id: int, file_path: str) -> Message:
    """Send a photo or document to the HR. Mirrors ``send_to_hr_chat``'s
    guards and race handling. The file is also copied into our ``media/``
    cache so the chat UI can render it without re-downloading from
    Telegram.
    """
    if (await bot._current_mode()) is BotMode.OFF:
        raise RuntimeError("Бот выключен. Включите DM Only или Full.")
    if bot._dry_run:
        raise RuntimeError("Отправка отключена: тестовый режим.")
    if telegram.SEND_LOCKED:
        raise RuntimeError("Отправка отключена: защита от случайной отправки.")

    src = Path(file_path)
    if not src.exists() or not src.is_file():
        raise RuntimeError(f"Файл не найден: {file_path}")

    async with bot._session_factory() as session:
        hr = await session.get(HR, hr_id)
        if hr is None:
            raise RuntimeError(f"HR id={hr_id} не найден.")
        target = hr.telegram_user_id or hr.telegram_username
        bl_value = await _hr_blacklist_value(session, hr)
    if target is None:
        raise RuntimeError(
            "У HR нет ни telegram_user_id, ни @username — нечем отправить."
        )
    if bl_value:
        raise RuntimeError(
            f"HR в blacklist ({bl_value}). Сначала уберите из blacklist."
        )

    as_photo = media.looks_like_photo(src)
    try:
        size = src.stat().st_size
    except OSError as e:
        raise RuntimeError(f"Не удалось прочитать файл: {e}")
    cap = media.PHOTO_SIZE_LIMIT if as_photo else media.DOCUMENT_SIZE_LIMIT
    if size > cap:
        mb_cap = cap // (1024 * 1024)
        kind_ru = "фото" if as_photo else "документ"
        raise RuntimeError(
            f"Слишком большой {kind_ru}: {size / (1024*1024):.1f} MB "
            f"> лимит {mb_cap} MB."
        )
    if as_photo:
        pyro_msg = await bot._client.send_photo(target, str(src))
    else:
        pyro_msg = await bot._client.send_document(target, str(src))
    logger.info(
        "Chat media sent to hr %d (tg_msg=%d, kind=%s, name=%s)",
        hr_id,
        pyro_msg.id,
        "photo" if as_photo else "document",
        src.name,
    )

    # Copy into our media cache. Path matches what `updates.on_dm_outgoing`'s
    # `download_media` would have written, so the racing handler that
    # downloads the same message can find the already-existing file
    # instead of re-fetching it from Telegram.
    ext = ".jpg" if as_photo else (src.suffix or ".bin")
    dest = media.media_cache_path(hr_id, pyro_msg.id, ext)
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        media_path = media.media_path_for_db(dest)
    except Exception:
        logger.exception(
            "media cache copy failed (or its folder could not be made)",
            extra={"hr_id": hr_id, "src": str(src), "dest": str(dest)},
        )
        media_path = None
    media_kind = "photo" if as_photo else "document"
    media_name = None if as_photo else src.name

    async with bot._session_factory() as session:
        row = Message(
            is_incoming=False,
            hr_id=hr_id,
            text="",
            tg_message_id=pyro_msg.id,
            sent_at=pyro_msg.date,
            media_kind=media_kind,
            media_path=media_path,
            media_name=media_name,
        )
        session.add(row)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            row = (
                await session.scalars(
                    select(Message).where(
                        Message.hr_id == hr_id,
                        Message.tg_message_id == pyro_msg.id,
                        Message.is_incoming.is_(False),
                    )
                )
            ).first()
            if row is None:
                raise
            return row
    return row
