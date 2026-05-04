import asyncio
import logging
from pathlib import Path

import numpy as np
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from adapters import lm_studio
from backend.domain import (
    check_blacklist,
    cosine_top_match,
    decide_vacancy_status,
    is_empty_vacancy,
    normalize_salary_to_rub_thousands,
    score_parsed,
)
from backend.helpers import (
    extract_dm_text,
    extract_text,
    fetch_telegram_avatar,
    resolve_hr_telegram,
)
from backend.llm import (
    CandidateLanguage,
    CandidateProfile,
    classify_hr_reply,
    generate_cover_letter,
    parse_vacancy,
    validate_vacancy_fit,
)
from backend.models import (
    Profile,
    ProfileLanguage,
    ProfileSkill,
    TelegramChannel,
    Vacancy,
    VacancyEvent,
    VacancyStatus,
)
from backend.payloads import ParsedVacancy
from backend.repository import (
    apply_classification,
    build_profile_block,
    delete_vacancy as _repo_delete_vacancy,
    find_known_hr,
    find_latest_vacancy_id_for_hr,
    find_or_create_company,
    find_or_create_hr,
    list_hrs_for_backfill,
    list_open_hr_chats,
    list_profile_languages,
    load_active_blacklist_patterns,
    load_profile_skills,
    get_profile,
    refresh_hr_username,
    save_incoming_message,
)


logger = logging.getLogger(__name__)


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
    text = extract_dm_text(msg)
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
            from backend.repository import _hr_blacklist_value
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
        from backend.bot import _classify_media, _download_media
        media_kind, media_name = _classify_media(msg)
        if media_kind is not None:
            media_path = await _download_media(client, msg, hr_lookup.id)

    avatar_bytes = None
    if client is not None and hr_lookup.avatar is None:
        avatar_bytes = await fetch_telegram_avatar(client, msg.from_user)

    async with session_factory() as session:
        try:
            hr = await find_known_hr(session, sender_id, sender_username)
            if hr is None:
                return
            # Backfill telegram_user_id when the HR was created via @username
            # only (Contacts/HR pane). First incoming DM is when we learn
            # their actual id — pin it so future lookups hit the fast path.
            if hr.telegram_user_id is None:
                hr.telegram_user_id = sender_id
            refresh_hr_username(hr, sender_username)
            if avatar_bytes is not None and hr.avatar is None:
                hr.avatar = avatar_bytes
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

    # С debounce-планировщиком (production-путь) — сообщение в буфере,
    # классификация отложена. Без планировщика (тесты / fallback) —
    # классифицируем inline как раньше.
    if schedule_classification is not None:
        schedule_classification(hr.id, vacancy_id, new_msg_id, text)
        return

    classification = await classify_hr_reply(text, lm_client, lm_chat_model)
    if classification is None:
        logger.info(
            "vacancy %s: classifier returned None, skipping status update",
            vacancy_id,
            extra={"vacancy_id": vacancy_id, "tg_message_id": msg.id},
        )
        return
    logger.info(
        "vacancy %s: classifier verdict=%s -> applying",
        vacancy_id,
        classification.status.value,
    )

    async with session_factory() as session:
        try:
            await apply_classification(
                session, vacancy_id, new_msg_id, classification
            )
            await session.commit()
            logger.info(
                "vacancy %s: classification committed (msg=%d)",
                vacancy_id,
                new_msg_id,
            )
        except Exception:
            logger.exception(
                "classification apply failed",
                extra={"vacancy_id": vacancy_id, "message_id": new_msg_id},
            )


async def catch_up_missed_dms(
    client,
    lm_client,
    lm_chat_model,
    session_factory,
    backfill_limit: int,
    *,
    on_message_persisted=None,
    on_vacancies_changed=None,
    schedule_classification=None,
) -> None:
    """Pull recent DM history per known HR, both directions.

    Outgoing messages cover the case where the user typed from their phone
    or another TG client while the bot was off — without this we'd only
    see what we sent from our own app + what HRs sent us, missing half the
    conversation. Dedup by ``UNIQUE (hr_id, tg_message_id, is_incoming)``;
    IntegrityError = «already had it», skip silently.

    Also reconciles deletes that happened while the bot was offline:
    Telegram doesn't replay ``DeletedMessagesHandler`` updates after a
    reconnect, so any local row whose ``tg_message_id`` falls inside the
    fetched window but is missing from Telegram's response is flipped to
    ``is_deleted=True`` here.
    """
    from datetime import datetime, timezone
    from sqlalchemy.exc import IntegrityError
    from backend.models import Message

    async with session_factory() as session:
        chats = await list_hrs_for_backfill(session)
    logger.info("DM catch-up: %d HR(s)", len(chats))
    new_msgs_total = 0
    tombstoned_total = 0
    for hr, _last_seen in chats:
        try:
            target = hr.telegram_user_id or hr.telegram_username
            if target is None:
                continue
            messages = []
            async for msg in client.get_chat_history(target, limit=backfill_limit):
                messages.append(msg)
            from backend.bot import _classify_media, _download_media
            had_new = False
            # Oldest-first so the chat order stays sane in the UI.
            for msg in reversed(messages):
                if msg.outgoing:
                    # Direct insert — outgoing doesn't need LLM classification.
                    text = extract_dm_text(msg)
                    media_kind, media_name = _classify_media(msg)
                    media_path = (
                        await _download_media(client, msg, hr.id)
                        if media_kind is not None else None
                    )
                    try:
                        async with session_factory() as session:
                            session.add(Message(
                                is_incoming=False,
                                hr_id=hr.id,
                                text=text,
                                tg_message_id=msg.id,
                                sent_at=msg.date,
                                media_kind=media_kind,
                                media_path=media_path,
                                media_name=media_name,
                            ))
                            await session.commit()
                        had_new = True
                    except IntegrityError:
                        pass  # already stored
                    except Exception:
                        logger.exception(
                            "catch_up outgoing insert failed",
                            extra={"hr_id": hr.id, "tg_message_id": msg.id},
                        )
                else:
                    # Incoming routed through the same pipeline as live DMs so
                    # classification + vacancy-linking stay consistent. The
                    # UNIQUE constraint inside save_incoming_message dedupes.
                    try:
                        await process_dm(
                            msg, lm_client, lm_chat_model, session_factory,
                            client=client,
                            schedule_classification=schedule_classification,
                        )
                        had_new = True
                        # С debounce-планировщиком статус НЕ меняется
                        # синхронно — он флипнется через 60с после burst'а.
                        # Тогда же отдельный таск пушит on_vacancies_changed
                        # сам. Не дублируем сигнал отсюда — в catch-up
                        # после OFF→active это особенно важно: 50 сообщений
                        # × 30 HR'ов = 1500 пушей за миллисекунду.
                        # Без планировщика (legacy путь) — классификация
                        # inline, тогда сигнал нужен.
                        if (
                            schedule_classification is None
                            and on_vacancies_changed is not None
                        ):
                            try:
                                on_vacancies_changed()
                            except Exception:
                                logger.exception(
                                    "catch_up: on_vacancies_changed hook failed"
                                )
                    except Exception:
                        logger.exception(
                            "catch_up incoming process failed",
                            extra={"hr_id": hr.id, "tg_message_id": msg.id},
                        )
            # Delete reconciliation. Window = ids covered by the fetched
            # history; anything in our DB inside that window not present in
            # the response was deleted while we were offline.
            tombstoned = False
            if messages:
                seen_ids = {m.id for m in messages}
                min_id = min(seen_ids)
                async with session_factory() as session:
                    local_rows = list(
                        (
                            await session.scalars(
                                select(Message).where(
                                    Message.hr_id == hr.id,
                                    Message.tg_message_id.is_not(None),
                                    Message.tg_message_id >= min_id,
                                    Message.is_deleted.is_(False),
                                )
                            )
                        ).all()
                    )
                    now = datetime.now(timezone.utc)
                    for row in local_rows:
                        if row.tg_message_id in seen_ids:
                            continue
                        row.is_deleted = True
                        if row.is_incoming and row.read_at is None:
                            row.read_at = now
                        tombstoned = True
                    if tombstoned:
                        await session.commit()
            if (had_new or tombstoned) and on_message_persisted is not None:
                try:
                    on_message_persisted(hr.id)
                except Exception:
                    logger.exception("on_message_persisted hook failed")
        except Exception:
            logger.exception(
                "catch_up failed for hr %d", hr.id, extra={"hr_id": hr.id}
            )


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


class IngestionPipeline:
    def __init__(
        self,
        client,
        session_factory,
        lm_client,
        lm_embed_client,
        lm_chat_model: str,
        lm_embed_model: str,
        send,
        runtime_settings,
    ) -> None:
        self._client = client
        self._session_factory = session_factory
        self._lm_client = lm_client
        self._lm_embed_client = lm_embed_client
        self._lm_chat_model = lm_chat_model
        self._lm_embed_model = lm_embed_model
        self._send = send
        self._rs = runtime_settings
        # Текстовый блок «Информация о кандидате» для cover-letter prompt'а.
        # Перестраивается в _reload_resources рядом с skills/blacklist.
        self._profile_block: str = ""
        self._embedding_ids: np.ndarray = np.empty((0,), dtype=np.int64)
        self._embedding_matrix: np.ndarray = np.empty((0, 0), dtype=np.float32)
        self._embedding_cache_loaded = False
        self._skills_cache: list[ProfileSkill] = []
        # Срез данных профиля для LLM-валидатора. Перестраивается в
        # _reload_resources вместе со skills/blacklist. До первой загрузки —
        # пустой профиль, валидатор подставит "—" во все слоты (равносильно
        # «нет ограничений»).
        self._profile_cache: CandidateProfile = CandidateProfile()
        self._blacklist_patterns: list[str] = []
        # Optional UI hook: called as on_progress(stage, label, current, total).
        # stage: "channel" — across channels in poll_active_channels;
        #        "message" — across messages inside the current channel.
        # Semantics: current = "how many already done", so it ranges 0..total.
        self.on_progress = None  # filled in by Bot.__init__ if running under the UI
        # Optional UI hook: called with no args after the title sweep at the
        # start of a poll cycle has written one or more title changes. Lets
        # the Contacts/Channels pane auto-refresh in real time without the
        # user having to switch tabs or restart the app.
        self.on_channels_changed = None
        # Optional UI hook: called with no args after a vacancy parse commit
        # that may have created/updated HR or Company rows (via
        # find_or_create_*). Drives real-time refresh of Contacts/HR and
        # Contacts/Companies lists during long poll cycles — а не только по
        # завершении ingestion_finished.
        self.on_contacts_changed = None
        # Optional UI hook: called with no args after любого commit'а,
        # который меняет состояние Vacancy (новая распарсенная вакансия,
        # delete, или DM-classifier изменил статус). Drives real-time
        # refresh вкладки «Вакансии» — push-аналог 5-сек polling-таймера,
        # который раньше был на JS-стороне.
        self.on_vacancies_changed = None

        # === DM burst-debounce =========================================
        # Юзеры (особенно русскоязычные) часто пишут одну мысль 3-5
        # короткими сообщениями подряд. Классификация каждой по отдельности
        # → лишние LLM-вызовы и шанс что верно классифицируется только
        # одно (часто последнее, но не всегда). Накапливаем 60 сек после
        # последнего сообщения от HR, потом одна классификация на склеенный
        # текст. Apply применяется к vacancy_id и msg_id ПОСЛЕДНЕГО
        # сообщения в burst'е.
        self._dm_classify_buffer: dict[int, list[dict]] = {}
        self._dm_classify_tasks: dict[int, asyncio.Task] = {}

    DM_CLASSIFY_DEBOUNCE_SEC = 60.0

    def schedule_dm_classification(
        self,
        hr_id: int,
        vacancy_id: int,
        msg_id: int,
        text: str,
    ) -> None:
        """Append text to per-HR burst buffer и (пере-)взводит таймер на
        DM_CLASSIFY_DEBOUNCE_SEC. Когда таймер дотикает (новых сообщений
        от HR не приходило), таск ``_run_debounced_classify`` соберёт
        пакет и сделает один LLM-вызов.
        """
        if not text:
            # Медиа-only без подписи нечем классифицировать. Пропускаем
            # тихо — само сообщение уже в БД.
            return
        buf = self._dm_classify_buffer.setdefault(hr_id, [])
        buf.append({"vacancy_id": vacancy_id, "msg_id": msg_id, "text": text})
        prev = self._dm_classify_tasks.get(hr_id)
        if prev is not None and not prev.done():
            prev.cancel()
        self._dm_classify_tasks[hr_id] = asyncio.create_task(
            self._run_debounced_classify(hr_id)
        )

    async def _run_debounced_classify(self, hr_id: int) -> None:
        try:
            await asyncio.sleep(self.DM_CLASSIFY_DEBOUNCE_SEC)
        except asyncio.CancelledError:
            return  # перепланировано более свежим сообщением — выходим тихо
        buf = self._dm_classify_buffer.pop(hr_id, [])
        # Identity-check: между sleep'ом и сюда мог прилететь новый
        # schedule_dm_classification, который положил в _dm_classify_tasks
        # уже ДРУГОЙ task. Снимать его из dict нельзя — иначе он останется
        # без strong-reference и asyncio может его собрать GC'м до выполнения.
        current = asyncio.current_task()
        if self._dm_classify_tasks.get(hr_id) is current:
            self._dm_classify_tasks.pop(hr_id, None)
        if not buf:
            return
        # Склеиваем тексты с двойным переносом — чтобы LLM видела границы
        # отдельных сообщений и могла выбрать самый продвинутый сигнал
        # (Offer > Invitation > Test > Decline > Answered) на ВСЕМ пакете.
        text = "\n\n".join(item["text"] for item in buf)
        last = buf[-1]
        vacancy_id = last["vacancy_id"]
        msg_id = last["msg_id"]
        try:
            classification = await classify_hr_reply(
                text, self._lm_client, self._lm_chat_model
            )
        except Exception:
            logger.exception(
                "debounced classify failed for hr %d (%d msgs)",
                hr_id, len(buf),
            )
            return
        if classification is None:
            logger.info(
                "vacancy %s: classifier returned None for hr %d (%d msgs in burst)",
                vacancy_id, hr_id, len(buf),
            )
            return
        logger.info(
            "vacancy %s: classifier verdict=%s -> applying (hr %d, %d msgs in burst)",
            vacancy_id, classification.status.value, hr_id, len(buf),
        )
        async with self._session_factory() as session:
            try:
                await apply_classification(
                    session, vacancy_id, msg_id, classification
                )
                await session.commit()
            except Exception:
                logger.exception(
                    "debounced classify apply failed",
                    extra={"vacancy_id": vacancy_id, "hr_id": hr_id},
                )
                return
        if self.on_vacancies_changed is not None:
            try:
                self.on_vacancies_changed()
            except Exception:
                logger.exception("on_vacancies_changed hook failed")

    async def cancel_pending_dm_classifications(self) -> None:
        """Кенсельнут все висящие debounce-таймеры (бот стопается / OFF /
        shutdown). asyncio.Task.cancel() — это hint, который сработает
        только если task сидит на await. Если он уже прошёл sleep и
        исполняет sync-блок (drain → classify → apply), cancel() — no-op,
        и task продолжит дёргать httpx-клиент / session_factory — которые
        могут уже быть закрыты в shutdown-пути. Поэтому ПОСЛЕ cancel'ов
        ждём с таймаутом, чтобы все живые task'и доработали или
        завершились по cancel'у. Накопленный текст пропадает; сами
        Message-row'ы остаются в БД — юзер увидит сообщения, статус
        придётся переклассифицировать вручную.
        """
        tasks = [t for t in self._dm_classify_tasks.values() if not t.done()]
        for t in tasks:
            t.cancel()
        if tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True),
                    timeout=5,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "cancel_pending_dm_classifications: %d task(s) did not finish within 5s",
                    sum(1 for t in tasks if not t.done()),
                )
        self._dm_classify_tasks.clear()
        self._dm_classify_buffer.clear()

    async def poll_active_channels(self) -> None:
        await self._reload_resources()
        # Берём ВСЕ каналы с @username (не только active=true): metadata-
        # sweep должен подтягивать title и аватарки и для выключенных
        # каналов тоже — они всё равно показываются в UI и пользователь
        # ожидает свежие данные. Активность гейтит только обработку
        # сообщений ниже.
        async with self._session_factory() as session:
            channels = (
                await session.scalars(
                    select(TelegramChannel).where(
                        TelegramChannel.username.is_not(None)
                    )
                )
            ).all()
        all_named = list(channels)

        # Быстрый sweep метаданных по всему списку до тяжёлой обработки
        # сообщений: один `get_chat` на канал, плюс backfill аватара через
        # `download_media`, всё пишется одной транзакцией. UI получает
        # свежие названия и аватары за десятки секунд, а не за десятки
        # минут (по ~5 мин на канал на парсинг сообщений).
        await self._refresh_channel_metadata(all_named)

        active_named = [c for c in all_named if c.is_active]
        total = len(active_named)
        logger.info(
            "Poll cycle start: %d named channels (%d active)",
            len(all_named),
            total,
        )
        for idx, ch in enumerate(active_named):
            self._emit_progress("channel", f"@{ch.username}", idx, total)
            try:
                await self._poll_channel(
                    ch.id, ch.username, ch.last_processed_msg_id
                )
            except Exception:
                logger.exception("[@%s] poll failed", ch.username)
        self._emit_progress("channel", "", total, total)
        # 0/0 on the message track signals the UI to clear that bar between
        # cycles; otherwise it would freeze on the last channel's count.
        self._emit_progress("message", "", 0, 0)
        logger.info("Poll cycle done")

    async def rerun_pipeline_for_vacancy(self, vacancy_id: int) -> bool:
        """Re-parse + re-classify an existing vacancy. UI's "прогнать заново".

        Reuses the original ``raw_text`` and source channel hint. Profile
        skills / blacklist are reloaded so the user can edit those and
        immediately re-evaluate vacancies under the new rules. Returns
        False if the vacancy is missing or has no raw_text.
        """
        async with self._session_factory() as session:
            v = await session.get(Vacancy, vacancy_id)
            if v is None:
                logger.warning("rerun: vacancy %d missing", vacancy_id)
                return False
            text = v.raw_text or ""
            channel_username = ""
            if v.source_channel_id is not None:
                ch = await session.get(TelegramChannel, v.source_channel_id)
                if ch is not None and ch.username:
                    channel_username = ch.username
        if not text:
            logger.warning("rerun: vacancy %d has empty raw_text", vacancy_id)
            return False
        await self._reload_resources()
        await self._parse_and_update_vacancy(
            vacancy_id, text, channel_username, allow_delete=False
        )
        return True

    async def recover_orphan_vacancies(self) -> int:
        """Finish parsing rows that were ingested but never made it through
        the LLM pipeline (process killed between ``_save_new_vacancy`` and
        ``_parse_and_update_vacancy`` commits, or LLM call cancelled).

        Called once at startup before the polling loop kicks in, so the
        UI never shows half-built rows for long. Each orphan goes through
        the auto-ingest path (``allow_delete=True``) — that's what would
        have happened on the original ingest if the process hadn't died.
        Trash / empty verdicts therefore delete the row, same as a fresh
        ingest. Returns the number of orphans processed.
        """
        await self._reload_resources()
        async with self._session_factory() as session:
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
            self._emit_progress(
                "recover", r.username or "", idx - 1, len(rows)
            )
            text = r.raw_text or ""
            if not text:
                continue
            try:
                await self._parse_and_update_vacancy(
                    r.id, text, r.username or "", allow_delete=True
                )
                processed += 1
            except Exception:
                logger.exception(
                    "recover: vacancy %d parse failed", r.id
                )
        # Clear the recovery bar once done so the next stage's progress
        # doesn't inherit the leftover count (mirrors poll_active_channels).
        self._emit_progress("recover", "", 0, 0)
        logger.info("recovered %d/%d orphan vacancy/vacancies", processed, len(rows))
        return processed

    def _emit_progress(self, stage: str, label: str, current: int, total: int) -> None:
        if self.on_progress is None:
            return
        try:
            self.on_progress(stage, label, current, total)
        except Exception:
            logger.exception("on_progress hook failed")

    async def poll_one_channel(self, channel_id: int) -> bool:
        """Run metadata refresh + message polling for a single channel.

        UI's «Прогнать сейчас» — taps this without touching the global
        poll loop, so it doesn't have to wait through 17 other channels
        in a 90-min cycle. Returns False if the row is missing/без
        username, либо если сам poll сломался (FloodWait, ChannelPrivate,
        LLM-таймаут) — то же поведение, что у глобального цикла, чтобы
        не давать `_dispatch` ловить и сжирать exception без `action`.
        """
        await self._reload_resources()
        async with self._session_factory() as session:
            ch = await session.get(TelegramChannel, channel_id)
            if ch is None or not ch.username:
                return False
            username = ch.username
            last_id = ch.last_processed_msg_id
        await self.refresh_channel_metadata_for_ids([channel_id])
        try:
            await self._poll_channel(channel_id, username, last_id)
        except Exception:
            logger.exception("[@%s] manual poll failed", username)
            return False
        return True

    async def refresh_channel_metadata_for_ids(self, channel_ids: list[int]) -> None:
        """Public entry point for one-off metadata refresh — например,
        после ручного «Добавить канал» из UI: сразу же тянем title/avatar,
        чтобы пользователь не ждал следующего поллинга.
        Делегирует во внутренний sweep, который и кидает on_channels_changed.
        """
        if not channel_ids:
            return
        logger.debug("refresh metadata for %d channel(s)", len(channel_ids))
        async with self._session_factory() as session:
            rows = (
                await session.scalars(
                    select(TelegramChannel).where(TelegramChannel.id.in_(channel_ids))
                )
            ).all()
        await self._refresh_channel_metadata(list(rows))

    async def _refresh_channel_metadata(self, channels) -> None:
        """Sweep metadata for every active channel before message polling.

        One `get_chat` call per channel (sequential — Pyrogram's session is
        not thread-safe and concurrent calls can trip FloodWait); the same
        response carries both ``title`` and ``photo``. Title is updated on
        every change; avatar is backfill-only (matches the HR policy in
        ``find_or_create_hr`` — once captured, we don't overwrite). All
        diffs land in a single transaction. Failures are logged and skipped.
        """
        title_updates: dict[int, str] = {}
        avatar_updates: dict[int, bytes] = {}
        for ch in channels:
            try:
                chat = await self._client.get_chat(ch.username)
            except Exception as e:
                logger.warning(
                    "[@%s] get_chat failed: %s: %s",
                    ch.username, type(e).__name__, e,
                )
                continue
            if chat is None:
                continue
            new_title = getattr(chat, "title", None)
            if new_title and new_title != ch.title:
                title_updates[ch.id] = new_title
            if ch.avatar is None and getattr(chat, "photo", None) is not None:
                blob = await fetch_telegram_avatar(self._client, chat)
                if blob:
                    avatar_updates[ch.id] = blob
        if not title_updates and not avatar_updates:
            return
        touched_ids = set(title_updates) | set(avatar_updates)
        async with self._session_factory() as session:
            for channel_id in touched_ids:
                db_ch = await session.get(TelegramChannel, channel_id)
                if db_ch is None:
                    continue
                new_title = title_updates.get(channel_id)
                if new_title is not None and db_ch.title != new_title:
                    db_ch.title = new_title
                blob = avatar_updates.get(channel_id)
                if blob is not None and db_ch.avatar is None:
                    db_ch.avatar = blob
            await session.commit()
        logger.info(
            "refresh_channel_metadata: %d title(s), %d avatar(s) updated",
            len(title_updates), len(avatar_updates),
        )
        if self.on_channels_changed is not None:
            try:
                self.on_channels_changed()
            except Exception:
                logger.exception("on_channels_changed hook failed")

    async def _poll_channel(
        self,
        channel_id: int,
        channel_username: str,
        last_id: int | None,
    ) -> None:
        new_msgs = []
        async for msg in self._client.get_chat_history(
            channel_username, limit=self._rs.backfill_limit
        ):
            if last_id is not None and msg.id <= last_id:
                break
            new_msgs.append(msg)

        ordered = list(reversed(new_msgs))
        total = len(ordered)
        for i, msg in enumerate(ordered):
            self._emit_progress("message", f"@{channel_username}", i, total)
            await self._ingest_post(channel_id, channel_username, msg)
        self._emit_progress("message", f"@{channel_username}", total, total)

    async def _ingest_post(
        self, channel_id: int, channel_username: str, msg
    ) -> None:
        text = extract_text(msg)
        if not text or msg.service is not None or msg.poll is not None:
            await self._advance_cursor(channel_id, msg.id)
            return

        try:
            embedding = await lm_studio.embed(
                self._lm_embed_client, self._lm_embed_model, text
            )
        except RuntimeError as e:
            logger.warning(
                "[@%s] %d embed shape error: %s, skipping",
                channel_username,
                msg.id,
                e,
            )
            await self._advance_cursor(channel_id, msg.id)
            return

        await self._ensure_embedding_cache()
        similar_id = cosine_top_match(
            np.asarray(embedding, dtype=np.float32),
            self._embedding_ids,
            self._embedding_matrix,
        )
        if similar_id is not None:
            # Could be a real duplicate, or the embedding of a vacancy left
            # half-built by a cancelled previous cycle (saved with raw_text
            # + embedding but no parsed fields). Detect the orphan and
            # finish parsing it now instead of skipping forever.
            unparsed = await self._is_unparsed_vacancy(similar_id)
            if unparsed:
                logger.info(
                    "[@%s] %d matched orphan vacancy %d, finishing parse",
                    channel_username, msg.id, similar_id,
                )
                # Note: if the orphan was originally ingested from a different
                # channel (cross-channel re-post), we parse using THIS post's
                # text + channel hint and stamp it onto the original row. The
                # embedding match guarantees texts are near-identical, so this
                # is acceptable.
                await self._parse_and_update_vacancy(
                    similar_id, text, channel_username
                )
            else:
                logger.info(
                    "[@%s] %d duplicate of vacancy %d, skipping",
                    channel_username, msg.id, similar_id,
                )
            await self._advance_cursor(channel_id, msg.id)
            return

        new_vacancy_id = await self._save_new_vacancy(
            channel_id, channel_username, msg, text, embedding
        )
        if new_vacancy_id is not None:
            await self._parse_and_update_vacancy(
                new_vacancy_id, text, channel_username
            )

        await self._advance_cursor(channel_id, msg.id)

    async def _save_new_vacancy(
        self,
        channel_id: int,
        channel_username: str,
        msg,
        text: str,
        embedding: list[float],
    ) -> int | None:
        async with self._session_factory() as session:
            try:
                new_vacancy = Vacancy(
                    source_channel_id=channel_id,
                    source_msg_id=msg.id,
                    raw_text=text,
                    embedding=embedding,
                    source_url=f"https://t.me/{channel_username}/{msg.id}",
                    posted_at=msg.date,
                )
                session.add(new_vacancy)
                await session.flush()
                session.add(
                    VacancyEvent(
                        vacancy_id=new_vacancy.id,
                        kind="ingested",
                        payload={
                            "channel": channel_username,
                            "msg_id": msg.id,
                        },
                    )
                )
                await session.commit()
                self._append_embedding(new_vacancy.id, embedding)
                logger.info(
                    "[@%s] %d -> vacancy %d",
                    channel_username,
                    msg.id,
                    new_vacancy.id,
                )
                return new_vacancy.id
            except IntegrityError:
                await session.rollback()
                logger.info(
                    "[@%s] %d uq_vacancy_source race, skipping",
                    channel_username,
                    msg.id,
                )
                return None

    async def _parse_and_update_vacancy(
        self,
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
            self._lm_client,
            self._lm_chat_model,
            channel_username=channel_username,
            known_skills=self._skills_cache,
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
                await self._delete_vacancy_as_trash(
                    vacancy_id, reason="empty: no meaningful fields"
                )
                return
            logger.info(
                "vacancy %s: empty vacancy (no meaningful fields), marking Not Fit (rerun, no auto-delete)",
                vacancy_id,
            )
            await self._save_empty_vacancy(vacancy_id, parsed)
            return

        # blacklist scans the FULL raw text; parse_vacancy truncates to 6000
        # chars due to LLM token budget — patterns past the cutoff still apply
        blacklist_match = check_blacklist(text, self._blacklist_patterns)
        # Score is computed over LLM-extracted required/preferred stack
        # (already canonicalized via {KNOWN_SKILLS_BLOCK}, deduped, capitalized).
        # required: +level / -1, preferred: +(level-1) / 0. See score_parsed.
        # ``parsed`` is guaranteed non-None here: ``is_empty_vacancy(None)`` is
        # True and we'd have returned above. ``assert`` is purely for type
        # narrowing.
        assert parsed is not None
        score = score_parsed(parsed, self._skills_cache)
        logger.debug(
            "vacancy %s: score=%d threshold=%d blacklist=%s",
            vacancy_id,
            score,
            self._rs.scoring_threshold,
            blacklist_match,
        )
        status, skip_reason = decide_vacancy_status(
            parsed, score, blacklist_match,
            threshold=self._rs.scoring_threshold,
        )

        if status == VacancyStatus.NEW:
            validation = await validate_vacancy_fit(
                parsed,
                text,
                self._lm_client,
                self._lm_chat_model,
                profile=self._profile_cache,
                known_skills=self._skills_cache,
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
                    await self._delete_vacancy_as_trash(
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
        if parsed.hr_contact:
            resolved_hr_user = await resolve_hr_telegram(
                self._client, parsed.hr_contact
            )
            if resolved_hr_user is not None:
                resolved_hr_avatar = await fetch_telegram_avatar(
                    self._client, resolved_hr_user
                )

        async with self._session_factory() as session:
            try:
                v = await session.get(Vacancy, vacancy_id)
                if v is None:
                    return

                v.status = status
                v.skip_reason = skip_reason
                v.score = score
                # Marks the row as fully populated by the LLM pipeline —
                # see ``Vacancy.is_parsed`` docstring. Set inside the same
                # transaction as the parsed fields so a crash after this
                # point still leaves the row consistent.
                v.is_parsed = True

                v.title = parsed.title
                v.description = parsed.description
                v.company_name = parsed.company_name
                v.hr_contact = parsed.hr_contact
                v.stack = parsed.stack
                v.grade = parsed.grade
                v.salary = parsed.salary
                v.salary_rub_min, v.salary_rub_max = (
                    normalize_salary_to_rub_thousands(parsed.salary)
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
                        lm_client=self._lm_client,
                        lm_model=self._lm_chat_model,
                    )
                    if company is not None:
                        v.company_id = company.id

                if resolved_hr_user is not None:
                    hr = await find_or_create_hr(
                        session, resolved_hr_user, avatar=resolved_hr_avatar
                    )
                    v.hr_id = hr.id
                    # Захватываем до выхода из сессии — нужно после commit
                    # для авто-отправки. session_factory с
                    # expire_on_commit=False, поэтому атрибуты hr остаются
                    # валидными после close.
                    hr_for_send = hr

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

        self._fire_contacts_changed()
        self._fire_vacancies_changed()

        # Авто-отправка отклика: вакансия прошла score-threshold + LLM-fit-
        # validator (status остался NEW), HR резолвлен в Telegram-юзера —
        # генерируем cover letter и отправляем с прикреплённым CV.
        if status == VacancyStatus.NEW and hr_for_send is not None:
            await self._send_application(hr_for_send, parsed, vacancy_id)

    async def _is_unparsed_vacancy(self, vacancy_id: int) -> bool:
        """A vacancy is 'orphaned' when its embedding row is in the cache
        but the LLM-pipeline never finished (parser cancelled, process
        crashed, LLM call failed silently). Reads the explicit
        ``is_parsed`` flag instead of inferring from ``title is None``
        because rerun-path empty/trash rows legitimately have no title
        but ARE parsed (status=NotFit, skip_reason='empty:...').
        """
        async with self._session_factory() as session:
            v = await session.get(Vacancy, vacancy_id)
        return v is not None and not v.is_parsed

    async def _advance_cursor(self, channel_id: int, msg_id: int) -> None:
        async with self._session_factory() as session:
            ch = await session.get(TelegramChannel, channel_id)
            if ch is None:
                return
            ch.last_processed_msg_id = msg_id
            await session.commit()

    async def _ensure_embedding_cache(self) -> None:
        if self._embedding_cache_loaded:
            return
        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    select(Vacancy.id, Vacancy.embedding).where(
                        Vacancy.embedding.is_not(None)
                    )
                )
            ).all()
        if rows:
            self._embedding_ids = np.array(
                [r.id for r in rows], dtype=np.int64
            )
            self._embedding_matrix = np.array(
                [r.embedding for r in rows], dtype=np.float32
            )
        self._embedding_cache_loaded = True
        logger.debug("Embedding cache loaded: %d vectors", len(rows))

    def _append_embedding(self, vacancy_id: int, embedding: list[float]) -> None:
        vec = np.asarray(embedding, dtype=np.float32)
        self._embedding_ids = np.append(self._embedding_ids, vacancy_id)
        if self._embedding_matrix.size == 0:
            self._embedding_matrix = vec.reshape(1, -1)
        else:
            self._embedding_matrix = np.vstack([self._embedding_matrix, vec])

    def _drop_embedding(self, vacancy_id: int) -> None:
        idx = np.where(self._embedding_ids == vacancy_id)[0]
        if idx.size == 0:
            return
        self._embedding_ids = np.delete(self._embedding_ids, idx)
        self._embedding_matrix = np.delete(self._embedding_matrix, idx, axis=0)

    async def _delete_vacancy(self, vacancy_id: int) -> None:
        # Route through the public repository delete so children
        # (vacancy_status_history, vacancy_event) are explicitly cleaned up
        # — SQLite has FK enforcement off in this engine, so a plain
        # session.delete(vacancy) would leave orphan rows.
        async with self._session_factory() as session:
            await _repo_delete_vacancy(session, vacancy_id)
            await session.commit()
        self._drop_embedding(vacancy_id)
        logger.info("vacancy %d: deleted from DB and embedding cache", vacancy_id)
        # Vacancy_count у HR/Company изменился — пушим refresh.
        self._fire_contacts_changed()
        self._fire_vacancies_changed()

    async def _delete_vacancy_as_trash(
        self, vacancy_id: int, reason: str | None
    ) -> None:
        """Auto-ingest trash deletion: ДО delete пишем строку в TrashEvent,
        чтобы потом было что показывать в per-channel статистике (без этого
        канал «прислал N мусора» не посчитать — Vacancy-ряд исчезает совсем).
        Channel/msg-id берём из самой вакансии, всё в одной транзакции.
        """
        from backend.repository import record_trash_event
        from backend.models import Vacancy as _V
        async with self._session_factory() as session:
            v = await session.get(_V, vacancy_id)
            channel_id = v.source_channel_id if v is not None else None
            msg_id = v.source_msg_id if v is not None else None
            await record_trash_event(
                session,
                source_channel_id=channel_id,
                source_msg_id=msg_id,
                reason=reason,
            )
            await _repo_delete_vacancy(session, vacancy_id)
            await session.commit()
        self._drop_embedding(vacancy_id)
        logger.info(
            "vacancy %d: deleted as trash (event recorded for channel=%s)",
            vacancy_id, channel_id,
        )
        self._fire_contacts_changed()
        self._fire_vacancies_changed()

    def _fire_contacts_changed(self) -> None:
        if self.on_contacts_changed is None:
            return
        try:
            self.on_contacts_changed()
        except Exception:
            logger.exception("on_contacts_changed hook failed")

    def _fire_vacancies_changed(self) -> None:
        if self.on_vacancies_changed is None:
            return
        try:
            self.on_vacancies_changed()
        except Exception:
            logger.exception("on_vacancies_changed hook failed")

    async def _save_empty_vacancy(
        self, vacancy_id: int, parsed: ParsedVacancy | None
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
        if parsed is not None and parsed.hr_contact:
            resolved_hr_user = await resolve_hr_telegram(
                self._client, parsed.hr_contact
            )
            if resolved_hr_user is not None:
                resolved_hr_avatar = await fetch_telegram_avatar(
                    self._client, resolved_hr_user
                )
        async with self._session_factory() as session:
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
                        normalize_salary_to_rub_thousands(parsed.salary)
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
                            lm_client=self._lm_client,
                            lm_model=self._lm_chat_model,
                        )
                        if company is not None:
                            v.company_id = company.id
                    if resolved_hr_user is not None:
                        hr = await find_or_create_hr(
                            session, resolved_hr_user, avatar=resolved_hr_avatar
                        )
                        v.hr_id = hr.id
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
                self._fire_contacts_changed()
                self._fire_vacancies_changed()
            except Exception:
                logger.exception(
                    "vacancy %s: empty-save failed",
                    vacancy_id,
                    extra={"vacancy_id": vacancy_id},
                )

    async def _reload_resources(self) -> None:
        async with self._session_factory() as session:
            self._skills_cache = await load_profile_skills(session)
            self._blacklist_patterns = await load_active_blacklist_patterns(
                session
            )
            profile = await get_profile(session)
            languages = await list_profile_languages(session)
            self._profile_cache = _build_candidate_profile(profile, languages)
            self._profile_block = await build_profile_block(session)
        logger.info(
            "loaded resources: %d skills, %d blacklist patterns, "
            "profile_title=%r, %d languages, profile_block=%d chars",
            len(self._skills_cache),
            len(self._blacklist_patterns),
            self._profile_cache.title,
            len(self._profile_cache.languages),
            len(self._profile_block),
        )

    def _cv_path(self):
        """Path к резюме (PDF), если задан в настройках. None если не задан
        или файл не существует — caller должен skip'нуть отправку."""
        raw = self._rs.cv_path
        if not raw:
            return None
        return Path(raw)

    async def _send_application(
        self,
        hr,
        parsed: ParsedVacancy,
        vacancy_id: int,
        *,
        force: bool = False,
    ) -> tuple[bool, str]:
        """Send cover letter + CV to hr for vacancy_id.

        Возвращает (ok, reason). reason — короткий код причины skip'а или
        'sent'. UI использует код для toast'а — иначе юзер не отличит
        реальную отправку от молчаливого skip'а (CV missing / SEND_LOCKED /
        LLM-провал и т.д.).
        """
        if not self._profile_block:
            logger.warning(
                "vacancy %d: profile_block empty, skipping send", vacancy_id
            )
            return False, "profile_empty"
        cover = await generate_cover_letter(
            self._profile_block, parsed, self._lm_client, self._lm_chat_model
        )
        if cover is None:
            logger.warning(
                "vacancy %d: cover letter generation failed, skipping send",
                vacancy_id,
            )
            return False, "cover_letter_failed"
        cv_path = self._cv_path()
        if cv_path is None or not cv_path.is_file():
            logger.warning(
                "vacancy %d: CV file missing (%s), skipping send",
                vacancy_id, cv_path,
            )
            return False, "cv_missing"
        try:
            sent = await self._send(
                hr, cover, attachment=cv_path, vacancy_id=vacancy_id,
                force=force,
            )
        except Exception:
            logger.exception(
                "vacancy %d: send failed",
                vacancy_id,
                extra={"vacancy_id": vacancy_id, "hr_id": hr.id},
            )
            return False, "telegram_error"
        if not sent:
            # Bot.send вернул False — что-то заблочило (SEND_LOCKED / OFF mode /
            # blacklist / dry_run). Конкретная причина лежит в логах warning'а
            # из Bot.send, нам нужен только factvalid.
            return False, "blocked"
        logger.info("vacancy %d: cover letter sent to hr %d", vacancy_id, hr.id)
        return True, "sent"

    async def send_application_for_vacancy(self, vacancy_id: int) -> tuple[bool, str]:
        """Manual cover-letter send (UI «Отправить отклик»). Reconstructs
        ParsedVacancy from the stored Vacancy row so the LLM-prompt has the
        same shape as the auto-send path. Returns (ok, reason). Reasons:
        'sent' / 'no_vacancy' / 'no_hr' / 'already_applied' / любой код
        из _send_application."""
        async with self._session_factory() as session:
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
        if not self._profile_block:
            await self._reload_resources()
        return await self._send_application(hr, parsed, vacancy_id, force=True)
