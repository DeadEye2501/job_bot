import asyncio
import logging
from pathlib import Path

import numpy as np
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from backend.flows import apply
from backend.flows import dm_classify
from backend.flows import channels
from backend.flows import rerun
from backend.flows import cleanup
from backend.domain.transitions import is_terminal_for_auto
from backend.helpers import (
    extract_dm_text,
    extract_text,
    fetch_telegram_avatar,
)
from backend.llm.candidate import CandidateProfile
from backend.llm.hr_reply import classify_hr_reply
from backend.models import (
    ProfileSkill,
    Vacancy,
)
from backend.repository.blacklist import load_active_blacklist_patterns
from backend.repository.hr_identify import find_known_hr, find_latest_vacancy_id_for_hr, refresh_hr_username, resolve_reply_target_vacancy
from backend.repository.hr_list import list_hrs_for_backfill
from backend.repository.messages import save_incoming_message
from backend.repository.profile import build_profile_block, get_profile, list_profile_languages, load_profile_skills
from backend.repository.vacancies_life import apply_classification


logger = logging.getLogger(__name__)


# DM catch-up batching: ``BATCH_SIZE`` HR'ов параллельно через
# ``asyncio.gather``, потом ``BATCH_DELAY_SEC`` пауза перед следующим
# батчем — чтобы TG-rate-limit window успевал сбрасываться. Параметры
# подобраны под flood_sleep_threshold=60 в adapters/telegram.py: даже
# если внутри батча словим короткий FloodWait, Pyrogram съест его сам.
_DM_CATCHUP_BATCH_SIZE = 20
_DM_CATCHUP_BATCH_DELAY_SEC = 1.0


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

    # State-machine gate: если вакансия уже в терминальном для авто-
    # классификатора статусе (Offer/Decline/Scam/Not Fit), вообще не
    # тратим LLM на её сообщения и не пишем призрачные строки в
    # vacancy_status_history. См. backend/domain/transitions.py.
    # Сообщение уже сохранено выше — это аудит-след входящего DM,
    # его и достаточно.
    async with session_factory() as session:
        v_status = await session.scalar(
            select(Vacancy.status).where(Vacancy.id == vacancy_id)
        )
    if v_status is not None and is_terminal_for_auto(v_status):
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

    classification = await classify_hr_reply(
        classify_text, v_status, lm_client, lm_chat_model
    )
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


async def backfill_hr_dm_history(
    client,
    hr,
    lm_client,
    lm_chat_model,
    session_factory,
    *,
    backfill_limit: int,
    on_message_persisted=None,
    on_vacancies_changed=None,
    schedule_classification=None,
) -> None:
    """Pull the DM history of one HR and persist it.

    Used by ``catch_up_missed_dms`` (per-HR loop) and the auto-apply path
    (when ``find_or_create_hr`` just minted a new HR — without this hook
    the chat would show only the cover-letter we just sent, prior history
    invisible until the next OFF→active transition).
    """
    from datetime import datetime, timezone
    from backend.models import Message
    from pyrogram.errors import FloodWait, PeerIdInvalid

    target = hr.telegram_user_id or hr.telegram_username
    if target is None:
        return
    messages = []
    try:
        async for msg in client.get_chat_history(target, limit=backfill_limit):
            messages.append(msg)
    except PeerIdInvalid:
        # Pyrogram peer-cache не знает этого id (HR добавлен по
        # @username без предыдущего DM, либо session сброшен).
        # Пробуем resolve по username, если есть; иначе skip.
        logger.warning(
            "backfill: PeerIdInvalid для hr %d (target=%s) — пробую "
            "resolve по @username",
            hr.id, target,
        )
        if hr.telegram_username:
            try:
                await client.get_users(hr.telegram_username)
                # После get_users peer попадает в cache; повторим
                # get_chat_history.
                messages = []
                async for msg in client.get_chat_history(
                    hr.telegram_username, limit=backfill_limit
                ):
                    messages.append(msg)
            except Exception as e:
                logger.warning(
                    "backfill: resolve fallback failed для hr %d: %s",
                    hr.id, e,
                )
                return
        else:
            return
    except FloodWait as e:
        # Pyrogram не съел FloodWait сам (значит, он длиннее
        # ``sleep_threshold`` из make_client). Ждём явно ровно столько,
        # сколько просит TG, и ретраим один раз — этого достаточно для
        # типичных peak'ов rate-limit'а во время batch catch-up'а. Если
        # и второй раз FloodWait — значит, реально серьёзный штраф,
        # дальше уже скипаем HR'а до следующего OFF→active цикла.
        wait = int(getattr(e, "value", 30))
        logger.info(
            "backfill: FloodWait %ds на hr %d — жду и ретраим",
            wait, hr.id,
        )
        await asyncio.sleep(wait + 1)
        try:
            messages = []
            async for msg in client.get_chat_history(target, limit=backfill_limit):
                messages.append(msg)
        except Exception:
            logger.exception(
                "backfill: retry после FloodWait не помог hr %d", hr.id,
            )
            return
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
                    "backfill outgoing insert failed",
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
                            "backfill: on_vacancies_changed hook failed"
                        )
            except Exception:
                logger.exception(
                    "backfill incoming process failed",
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
    async with session_factory() as session:
        chats = await list_hrs_for_backfill(session)
    logger.info(
        "DM catch-up: %d HR(s), batch=%d delay=%ss",
        len(chats), _DM_CATCHUP_BATCH_SIZE, _DM_CATCHUP_BATCH_DELAY_SEC,
    )
    # Батчим, чтобы 300-500 HR'ов не превращались в 300-500 последовательных
    # RPC'ов с заметной wall-time'ой. ``asyncio.gather`` внутри батча —
    # параллельно; пауза между батчами даёт TG-rate-limit'у выдохнуть.
    for batch_start in range(0, len(chats), _DM_CATCHUP_BATCH_SIZE):
        batch = chats[batch_start:batch_start + _DM_CATCHUP_BATCH_SIZE]
        results = await asyncio.gather(
            *[
                backfill_hr_dm_history(
                    client, hr, lm_client, lm_chat_model, session_factory,
                    backfill_limit=backfill_limit,
                    on_message_persisted=on_message_persisted,
                    on_vacancies_changed=on_vacancies_changed,
                    schedule_classification=schedule_classification,
                )
                for hr, _last_seen in batch
            ],
            return_exceptions=True,
        )
        for (hr, _), result in zip(batch, results):
            if isinstance(result, Exception):
                logger.exception(
                    "catch_up failed for hr %d", hr.id,
                    exc_info=result,
                )
        if batch_start + _DM_CATCHUP_BATCH_SIZE < len(chats):
            await asyncio.sleep(_DM_CATCHUP_BATCH_DELAY_SEC)


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
        # Optional UI hook: called as on_new_message(hr_id) после persist'а
        # сообщения (в т.ч. backfill'ом нового HR'а из автоаплая). Bot
        # форвардит сюда свой self.on_new_message, чтобы IngestionPipeline
        # мог толкать chat-update без обратной зависимости на Bot.
        self.on_new_message = None

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
        # Семафор на одновременные LLM-классификации. Catch-up на OFF→active
        # transition'е может разом разбудить debounce'ры по всем HR'ам, что
        # на локальной LM Studio превращается в 30 параллельных httpx.post
        # к одному серверу — она ставит их в очередь, начинает таймаутить и
        # часть вердиктов теряется. 2 одновременных вызова — компромисс
        # между throughput'ом и не-OOM'нуть LM Studio.
        self._dm_classify_semaphore = asyncio.Semaphore(2)

        # Strong-references на in-flight per-HR backfill таски (kicked
        # из _spawn_hr_backfill). Event loop держит на тасках только
        # weak-ref'ы — без своего set'а Python может GC'нуть таск
        # посреди выполнения с warning'ом «Task was destroyed but it
        # is pending». На done-callback'е сам себя убираем из set'а.
        self._backfill_tasks: set[asyncio.Task] = set()

        # Shutdown-флаг. Bot.run finally выставляет его в True ДО
        # client.stop() / lm_*.aclose() — после этого schedule_dm_class*
        # и process_dm молча no-op'ят, чтобы Pyrogram'овский handler,
        # успевший отстрелить уже после teardown'а, не насыпал в БД
        # запись и не попытался дёрнуть закрытый httpx-клиент.
        self._shutting_down: bool = False

    def mark_shutting_down(self) -> None:
        """Bot.run finally: с этого момента DM-handler ничего не делает."""
        self._shutting_down = True
        for task in self._backfill_tasks:
            task.cancel()


    DM_CLASSIFY_DEBOUNCE_SEC = 60.0
    # Cap buffer'а на одного HR — защита от спама. 50 сообщений в одном
    # debounce-окне (60с) уже точно ненормально; накопление тысяч строк
    # раздувает память и rам прибавляет ничего полезного — LLM всё равно
    # отрежет хвост в classify_hr_reply.
    DM_CLASSIFY_BUFFER_CAP = 50


    def _emit_progress(self, stage: str, label: str, current: int, total: int) -> None:
        if self.on_progress is None:
            return
        try:
            self.on_progress(stage, label, current, total)
        except Exception:
            logger.exception("on_progress hook failed")


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

    def _spawn_hr_backfill(self, hr) -> None:
        """Per-HR DM backfill kicked when a freshly-created HR is wired up
        from a parsed vacancy. Runs as a background task so the parse loop
        doesn't block on Telegram history fetch + media downloads. Pushes
        ``on_new_message`` per HR once the rows land — open chat in UI
        fills in without restart.

        Wajne: вызывать ПОСЛЕ ``_try_auto_send`` для свежесозданного HR'а,
        иначе backfill может догнать через ``get_chat_history`` cover-
        letter сообщение раньше, чем ``Bot.send`` закоммитит свою row,
        и вставит её без ``vacancy_id`` (UNIQUE на (hr_id, tg_message_id,
        is_incoming) потом отстрелит Bot.send'овский insert).
        """
        async def _run() -> None:
            try:
                await backfill_hr_dm_history(
                    self._client, hr, self._lm_client, self._lm_chat_model,
                    self._session_factory,
                    backfill_limit=self._rs.dm_backfill_limit,
                    on_message_persisted=self.on_new_message,
                    on_vacancies_changed=self.on_vacancies_changed,
                    schedule_classification=self.schedule_dm_classification,
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(
                    "spawn_hr_backfill failed for hr %d",
                    hr.id, extra={"hr_id": hr.id},
                )
        task = asyncio.create_task(_run())
        self._backfill_tasks.add(task)
        task.add_done_callback(self._backfill_tasks.discard)


    async def _reload_resources(self) -> None:
        # Кэши skills/blacklist/profile/languages/profile_block обновляются
        # ровно один раз — в начале каждого poll-цикла. Если юзер редактирует
        # профиль через UI между циклами, изменения подхватятся ТОЛЬКО на
        # следующем `poll_active_changes`. Это намеренно: cache invalidation
        # из UI-bridge'а потребует cross-thread hook'а, и польза маргинальная
        # (юзер редко редактирует профиль во время активного полла).
        async with self._session_factory() as session:
            self._skills_cache = await load_profile_skills(session)
            self._blacklist_patterns = await load_active_blacklist_patterns(
                session
            )
            profile = await get_profile(session)
            languages = await list_profile_languages(session)
            self._profile_cache = apply._build_candidate_profile(profile, languages)
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


    async def check_ghosting_timeouts(self):
        return await cleanup.check_ghosting_timeouts(self)

    async def rerun_pipeline_for_vacancy(self, vacancy_id):
        return await rerun.rerun_pipeline_for_vacancy(self, vacancy_id)

    async def recover_orphan_vacancies(self):
        return await rerun.recover_orphan_vacancies(self)

    async def poll_active_channels(self):
        return await channels.poll_active_channels(self)

    async def poll_one_channel(self, channel_id):
        return await channels.poll_one_channel(self, channel_id)

    async def refresh_channel_metadata_for_ids(self, channel_ids):
        return await channels.refresh_channel_metadata_for_ids(self, channel_ids)

    def update_dm_buffer_text(self, hr_id, msg_id, new_text):
        return dm_classify.update_dm_buffer_text(self, hr_id, msg_id, new_text)

    def remove_dm_buffer_msg(self, hr_id, msg_id):
        return dm_classify.remove_dm_buffer_msg(self, hr_id, msg_id)

    def schedule_dm_classification(self, hr_id, vacancy_id, msg_id, text):
        return dm_classify.schedule_dm_classification(self, hr_id, vacancy_id, msg_id, text)

    async def cancel_pending_dm_classifications(self, *, drain=False):
        return await dm_classify.cancel_pending_dm_classifications(self, drain=drain)

    async def send_application_for_vacancy(self, vacancy_id):
        return await apply.send_application_for_vacancy(self, vacancy_id)
