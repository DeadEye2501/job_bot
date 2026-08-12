"""Повторный разбор уже заведённой вакансии."""

import logging

from sqlalchemy import select

from backend.flows import parse
from backend.message_text import extract_text
from backend.models import TelegramChannel
from backend.models import Vacancy
from backend.repository.channels import list_named_channels

logger = logging.getLogger(__name__)


async def rerun_pipeline_for_vacancy(pipeline, vacancy_id: int) -> bool:
    """Re-parse + re-classify an existing vacancy. UI's "прогнать заново".

    По возможности **повторно фетчим оригинальный пост из Telegram**
    (по `source_channel_id` + `source_msg_id`) и сохраняем свежий
    ``raw_text`` в БД до повторного парса. Это даёт «полностью
    переобработать заново»-семантику, которую юзер ожидает: если
    пост был отредактирован в канале, рерана увидит актуальный
    текст; если нет — поведение идентично старому. Fallback на
    кешированный ``v.raw_text`` срабатывает, когда канал/сообщение
    недоступны (FloodWait, удалено, нет ни id ни username).
    Profile skills / blacklist тоже переподгружаются,
    чтобы юзер мог отредактировать их и сразу пере-оценить вакансии
    под новые правила. Returns False если вакансии нет или у неё
    пустой ``raw_text`` (и Telegram-фетч тоже ничего не дал).
    """
    async with pipeline._session_factory() as session:
        v = await session.get(Vacancy, vacancy_id)
        if v is None:
            logger.warning("rerun: vacancy %d missing", vacancy_id)
            return False
        cached_text = v.raw_text or ""
        channel_username = ""
        source_msg_id = v.source_msg_id
        if v.source_channel_id is not None:
            named = await list_named_channels(
                session, ids=[v.source_channel_id]
            )
            if named:
                channel_username = named[0].username

    from pyrogram.errors import FloodWait

    fresh_text: str | None = None
    if channel_username and source_msg_id is not None:
        try:
            msg = await pipeline._client.get_messages(
                channel_username, message_ids=source_msg_id
            )
            if msg is not None and not getattr(msg, "empty", False):
                candidate = extract_text(msg)
                if candidate:
                    fresh_text = candidate
                else:
                    logger.info(
                        "rerun: vacancy %d fetched msg @%s/%d but text is empty (media-only?), keeping cached raw_text",
                        vacancy_id, channel_username, source_msg_id,
                    )
            else:
                logger.info(
                    "rerun: vacancy %d msg @%s/%d not available (deleted/empty), keeping cached raw_text",
                    vacancy_id, channel_username, source_msg_id,
                )
        except FloodWait as e:
            logger.warning(
                "rerun: vacancy %d FloodWait %ss while fetching @%s/%d, keeping cached raw_text",
                vacancy_id, e.value, channel_username, source_msg_id,
            )
        except Exception:
            logger.exception(
                "rerun: vacancy %d failed to refetch @%s/%d, keeping cached raw_text",
                vacancy_id, channel_username, source_msg_id,
            )

    if fresh_text is not None and fresh_text != cached_text:
        # Свежий raw_text коммитится отдельной транзакцией ДО парса,
        # т.е. при сбое/cancel'е парса в БД останется новый raw_text
        # рядом со stale parsed-полями (title/stack/score из прошлого
        # прогона). Это самовосстанавливается на следующем rerun:
        # парс прогонится по уже свежему тексту. Лучше иметь
        # актуальный raw_text для будущих ретраев, чем держать
        # старый текст и парс синхронно — у юзера всё равно нет
        # «частично-обновлённой» семантики.
        async with pipeline._session_factory() as session:
            v = await session.get(Vacancy, vacancy_id)
            if v is not None:
                v.raw_text = fresh_text
                await session.commit()
        text = fresh_text
    else:
        text = cached_text

    if not text:
        logger.warning("rerun: vacancy %d has empty raw_text", vacancy_id)
        return False
    await pipeline._reload_resources()
    await parse.parse_and_update_vacancy(pipeline, 
        vacancy_id, text, channel_username, allow_delete=False
    )
    return True


async def recover_orphan_vacancies(pipeline) -> int:
    """Finish parsing rows that were ingested but never made it through
    the LLM pipeline (process killed between ``save_new_vacancy`` and
    ``parse_and_update_vacancy`` commits, or LLM call cancelled).

    Called once at startup before the polling loop kicks in, so the
    UI never shows half-built rows for long. Each orphan goes through
    the auto-ingest path (``allow_delete=True``) — that's what would
    have happened on the original ingest if the process hadn't died.
    Trash / empty verdicts therefore delete the row, same as a fresh
    ingest. Returns the number of orphans processed.
    """
    await pipeline._reload_resources()
    async with pipeline._session_factory() as session:
        rows = (
            await session.execute(
                select(
                    Vacancy.id,
                    Vacancy.raw_text,
                    TelegramChannel.username,
                )
                .outerjoin(
                    TelegramChannel,
                    Vacancy.source_channel_id == TelegramChannel.id,
                )
                .where(
                    Vacancy.is_parsed.is_(False),
                    Vacancy.raw_text.is_not(None),
                )
                .order_by(Vacancy.id.asc())
            )
        ).all()
    if not rows:
        return 0
    logger.info("recovering %d orphan vacancy/vacancies", len(rows))
    processed = 0
    for idx, r in enumerate(rows, start=1):
        pipeline._emit_progress(
            "recover", r.username or "", idx - 1, len(rows)
        )
        text = r.raw_text or ""
        if not text:
            continue
        try:
            await parse.parse_and_update_vacancy(pipeline, 
                r.id, text, r.username or "", allow_delete=True
            )
            processed += 1
        except Exception:
            logger.exception(
                "recover: vacancy %d parse failed", r.id
            )
    # Clear the recovery bar once done so the next stage's progress
    # doesn't inherit the leftover count (mirrors poll_active_channels).
    pipeline._emit_progress("recover", "", 0, 0)
    logger.info("recovered %d/%d orphan vacancy/vacancies", processed, len(rows))
    return processed
