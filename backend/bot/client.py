"""Bot class — long-running pyrogram client + ingestion loop.

Entry point for the application is at the project root: ``main.py``.
This module only defines the ``Bot`` class; ``main.py`` is what wires
schema-migration / wizard / Bot construction together.
"""

import asyncio
import logging

from pyrogram import filters
from pyrogram.handlers import (
    DeletedMessagesHandler,
    EditedMessageHandler,
    MessageHandler,
    RawUpdateHandler,
)
# Module-top so the raw-update handler doesn't pay a sys.modules lookup per
# server event. Aliased with leading underscore — these are only consumed
# inside ``_on_raw_update``.
from pyrogram.raw.types import (
    PeerUser as _PeerUser,
    UpdateReadHistoryOutbox as _UpdateReadHistoryOutbox,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from adapters import lm_studio, telegram
from backend.bot import send
from backend.bot import chat
from backend.bot import channels
from backend.bot import media
from backend.flows.dm import catch_up_missed_dms, process_dm
from backend.flows.pipeline import IngestionPipeline
from backend.helpers import extract_dm_text, extract_text
from backend.repository.hr_identify import find_known_hr
from backend.models import (
    BotMode,
    Message,
)
from backend.runtime_settings import RuntimeSettings


logger = logging.getLogger(__name__)




class Bot:
    def __init__(
        self,
        runtime_settings: RuntimeSettings,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        dry_run: bool = False,
    ) -> None:
        self._dry_run = dry_run
        if runtime_settings.tg is None:
            raise RuntimeError("Bot: TG account not configured")
        if runtime_settings.chat is None:
            raise RuntimeError("Bot: chat LLM not configured")
        if runtime_settings.embed is None:
            raise RuntimeError("Bot: embedding LLM not configured")

        self._rs = runtime_settings
        self._session_factory = session_factory

        # If construction fails partway through, any half-built httpx
        # clients will be closed by GC (with a ResourceWarning). We don't
        # try to clean them up here because httpx has no sync close() and
        # we can't await from sync __init__ — and init failure means the
        # process is about to exit anyway.
        self._client = telegram.make_client(runtime_settings.tg)
        self._lm_client = lm_studio.make_client(runtime_settings.chat)
        self._lm_chat_model = runtime_settings.chat.model
        # Reuse the chat httpx client for embeddings if both providers point
        # at the same endpoint with the same auth.
        self._lm_embed_client = (
            self._lm_client
            if send._shares_provider(runtime_settings.chat, runtime_settings.embed)
            else lm_studio.make_client(runtime_settings.embed)
        )
        self._lm_embed_model = runtime_settings.embed.model

        self._ingestion = IngestionPipeline(
            client=self._client,
            session_factory=self._session_factory,
            lm_client=self._lm_client,
            lm_embed_client=self._lm_embed_client,
            lm_chat_model=self._lm_chat_model,
            lm_embed_model=self._lm_embed_model,
            send=self.send,
            runtime_settings=self._rs,
        )
        self._client.add_handler(
            MessageHandler(self._on_dm, filters.private & filters.incoming)
        )
        self._client.add_handler(
            MessageHandler(
                self._on_dm_outgoing, filters.private & filters.outgoing
            )
        )
        self._client.add_handler(
            EditedMessageHandler(self._on_dm_edit, filters.private)
        )
        # NOTE: `filters.private` НЕ годится для DeletedMessagesHandler.
        # Pyrogram'овский parse_deleted_messages для UpdateDeleteMessages
        # (все приватные удаления) ставит msg.chat=None — peer info в этом
        # апдейте не приходит. filters.private требует m.chat.type in
        # {PRIVATE, BOT}, и для chat=None даёт False — handler не срабатывает
        # вообще. Поэтому пропускаем chatless-stub'ы и явные private-чаты,
        # отсекая каналы (UpdateDeleteChannelMessages приходит уже с
        # chat=Channel).
        self._client.add_handler(
            DeletedMessagesHandler(
                self._on_dm_delete,
                filters.private | filters.create(
                    lambda _, __, m: getattr(m, "chat", None) is None
                ),
            )
        )
        # UpdateReadHistoryOutbox carries the «HR has read up to msg N» signal
        # for our outgoing DMs. Filter out everything else inside the handler;
        # raw updates fire for every server event.
        self._client.add_handler(RawUpdateHandler(self._on_raw_update))

        # Wake event = "skip the rest of the current sleep, poll now". Set
        # by kick(). Stop event = "shutdown after current iteration". Set
        # by stop().
        self._wake_event = asyncio.Event()
        self._stop_event = asyncio.Event()
        # Capture loop в run() — нужен для thread-safe kick / cancel /
        # request_stop из Qt-треда. Эти Event-ы и Task-и живут на
        # runner-loop'е; .set() / .cancel() из чужого треда — undefined
        # behavior (CPython его прощает, но контракт asyncio нарушается).
        self._loop: asyncio.AbstractEventLoop | None = None
        # Optional UI hooks fired around each Full-mode poll cycle.
        self.on_cycle_start = None  # filled in by client.bridge.MainApi if running under the UI
        self.on_cycle_end = None    # filled in by client.bridge.MainApi if running under the UI
        # Forwarded from IngestionPipeline; Bridge wires this to a Qt signal.
        # Signature: on_progress(stage, label, current, total)
        self.on_progress = None     # filled in by client.bridge.MainApi if running under the UI
        # Real-time chat push — fires after a new incoming HR DM is saved.
        # Signature: on_new_message(hr_id: int). Bridge wires to a Qt signal
        # the Contacts/HR pane listens for.
        self.on_new_message = None
        # Real-time HR-read-receipt push. Signature:
        # on_hr_read(hr_id: int, max_tg_id: int). Cheaper than on_new_message
        # because the UI only needs to flip ✓ → ✓✓ on already-rendered rows
        # rather than refetch the whole chat.
        self.on_hr_read = None
        # Real-time push for the Contacts/Channels pane: fires once per poll
        # cycle, right after the title sweep writes any new titles into the
        # DB. UI re-fetches the list so the user sees fresh names without
        # having to switch tabs or restart.
        self.on_channels_changed = None
        # Real-time push for Contacts/HR + Contacts/Companies: fires after
        # каждой commit'а с парсингом вакансии, который мог через
        # find_or_create_* создать/обновить HR/Company. Дёргается во время
        # длинных циклов (90 минут на 18 каналов), а не только по
        # завершении ingestion_finished.
        self.on_contacts_changed = None
        # Real-time push для вкладки «Вакансии». Заменяет 5-сек JS-таймер:
        # каждый раз когда в БД меняется Vacancy — фронт сразу делает
        # refetch.
        self.on_vacancies_changed = None
        self._ingestion.on_progress = lambda stage, label, cur, tot: (
            self.on_progress and self.on_progress(stage, label, cur, tot)
        )
        self._ingestion.on_channels_changed = lambda: (
            self.on_channels_changed and self.on_channels_changed()
        )
        self._ingestion.on_contacts_changed = lambda: (
            self.on_contacts_changed and self.on_contacts_changed()
        )
        self._ingestion.on_vacancies_changed = lambda: (
            self.on_vacancies_changed and self.on_vacancies_changed()
        )
        self._ingestion.on_new_message = lambda hr_id: (
            self.on_new_message and self.on_new_message(hr_id)
        )
        # Reference to the currently-running poll task so the UI's stop
        # button can cancel it without killing the whole bot loop.
        self._current_poll_task: asyncio.Task | None = None

    @property
    def is_ready(self) -> bool:
        """True after Bot.run() прошёл await client.start() и захватил loop.
        До этой точки Pyrogram-клиент ещё не подключён, и любой
        ``self._bot.<method>()`` из Qt-треда может попасть в полу-
        инициализированное состояние. Используйте этот флаг для
        gate-проверок (`if bot is not None and bot.is_ready: ...`)."""
        return self._loop is not None

    def kick(self) -> None:
        """Wake the loop so the next poll runs immediately instead of waiting.

        Thread-safe: вызывается из Qt-треда. Через ``call_soon_threadsafe``
        планируем .set() на runner-loop'е, чтобы не мутить Event из чужого
        треда напрямую (asyncio.Event внутри ходит по _waiters и пытается
        loop.call_soon — без call_soon_threadsafe это иногда роняет).
        """
        logger.debug("Poll wake requested")
        loop = self._loop
        if loop is not None and not loop.is_closed():
            loop.call_soon_threadsafe(self._wake_event.set)
        else:
            self._wake_event.set()


    def request_stop(self) -> None:
        """Ask the loop to exit after the current iteration.

        Thread-safe: см. ``kick``.
        """
        logger.info("Stop requested")
        loop = self._loop
        if loop is not None and not loop.is_closed():
            loop.call_soon_threadsafe(self._stop_event.set)
            loop.call_soon_threadsafe(self._wake_event.set)
        else:
            self._stop_event.set()
            self._wake_event.set()

    async def log_out_session(self) -> None:
        """Revoke server-side TG session via DROP_AUTH and exit the run loop.

        Pyrogram's log_out() also disconnects the client and removes the
        local session file. Errors are logged but don't propagate — the
        caller still wants the bot to stop and the local creds cleared.
        """
        logger.info("TG log_out requested")
        try:
            await self._client.log_out()
        except Exception:
            logger.exception("log_out RPC failed; proceeding to stop bot")
        self._stop_event.set()
        self._wake_event.set()

    async def _current_mode(self) -> BotMode:
        try:
            return await self._rs.get_mode()
        except Exception:
            logger.exception("get_mode failed; falling back to Off")
            return BotMode.OFF

    async def run(self, *, once: bool = False) -> None:
        if self._dry_run:
            logger.warning("DRY-RUN mode: outgoing TG messages will NOT be sent")
        # Синкаем dev-safety lock из БД-настройки в module-level guard
        # adapters/telegram.send_dm. Авторитет — rs.send_locked; константа
        # — defence-in-depth на случай если Bot.send забудет проверить.
        telegram.SEND_LOCKED = self._rs.send_locked
        if telegram.SEND_LOCKED:
            logger.warning(
                "SEND_LOCKED=True: outgoing DM will be simulated, not sent"
            )
        await self._client.start()
        # ``self._loop`` ставим ПОСЛЕ client.start() — это и метка
        # «бот готов принимать kick/cancel из Qt-треда», и сам loop
        # для thread-safe методов. До этого момента kick/cancel/
        # request_stop fallback'ятся на прямой .set() (безопасно: Event
        # ещё не имеет ожидателей; а poll-task ещё не создан, так что
        # и cancel'ить нечего).
        self._loop = asyncio.get_running_loop()
        from backend.runtime_settings import _mask_phone
        logger.info(
            "Telegram client connected (phone=%s)",
            _mask_phone(self._rs.tg.phone if self._rs.tg else None),
        )
        await self._persist_session_if_changed()
        try:
            # Re-parse any vacancies that were ingested but never finished
            # the LLM pipeline (previous process crashed mid-parse). Runs
            # before polling so the UI doesn't briefly show empty rows
            # alongside fresh ones, and so a long-stuck orphan eventually
            # gets unstuck even if its source channel never re-posts the
            # same message.
            try:
                await self._ingestion.recover_orphan_vacancies()
            except Exception:
                logger.exception("orphan recovery failed")
            # OFF is a full stop — no DM catch-up, no LLM classification,
            # no polling. Catch-up runs once on every transition into an
            # active mode (including the initial transition from the seeded
            # OFF state at process start), so a fresh start in DM Only / Full
            # back-fills immediately and so does toggling out of OFF later.
            prev_mode = BotMode.OFF
            while True:
                mode = await self._current_mode()
                # Transition в OFF: гасим debounce-таймеры pending'овых
                # классификаций. Накопленные тексты пропадают, но сами
                # сообщения уже в БД — юзеру нужно будет переклассифицировать
                # вручную через UI если нужно.
                if mode is BotMode.OFF and prev_mode is not BotMode.OFF:
                    logger.info("Transition into OFF; draining DM debouncers")
                    await self._ingestion.cancel_pending_dm_classifications(drain=True)
                if mode is not BotMode.OFF and prev_mode is BotMode.OFF:
                    logger.info(
                        "Transition into active mode (%s); running DM catch-up",
                        mode.value,
                    )
                    try:
                        await catch_up_missed_dms(
                            self._client,
                            self._lm_client,
                            self._lm_chat_model,
                            self._session_factory,
                            backfill_limit=self._rs.dm_backfill_limit,
                            on_message_persisted=self.on_new_message,
                            on_vacancies_changed=self.on_vacancies_changed,
                            schedule_classification=self._ingestion.schedule_dm_classification,
                        )
                    except Exception:
                        logger.exception("dm catch-up failed")
                # Ghosting timer: дёргается каждый tick в активных
                # режимах (DM_ONLY и FULL). В OFF не запускается — бот
                # на паузе, не должен сам менять статусы. Сама проверка
                # дешёвая: только Applied/In Progress попадают в шорт-
                # лист, и при пустом списке ранний return.
                if mode is not BotMode.OFF:
                    try:
                        await self._ingestion.check_ghosting_timeouts()
                    except Exception:
                        logger.exception("ghosting timer tick failed")
                # Channel polling and outbound applications are Full-only.
                # DM Only and Off both skip ingestion (DM Only still reacts
                # to incoming HR messages via the registered MessageHandler).
                if mode is BotMode.FULL and self._current_poll_task is None:
                    # Гард от клоббера: если ручной `poll_channel_now` или
                    # `force_poll_once` сейчас держит слот, не перетираем
                    # его новой задачей — иначе обе крутятся параллельно
                    # и гонят embedding-кэш и курсоры каналов.
                    if self.on_cycle_start is not None:
                        try: self.on_cycle_start()
                        except Exception: logger.exception("on_cycle_start hook failed")
                    try:
                        self._current_poll_task = asyncio.create_task(
                            self._ingestion.poll_active_channels()
                        )
                        try:
                            await self._current_poll_task
                        except asyncio.CancelledError:
                            logger.info("poll cycle cancelled by user")
                    except Exception:
                        logger.exception("poll cycle failed")
                    finally:
                        self._current_poll_task = None
                        if self.on_cycle_end is not None:
                            try: self.on_cycle_end()
                            except Exception: logger.exception("on_cycle_end hook failed")
                prev_mode = mode
                if once or self._stop_event.is_set():
                    # finally-блок ниже логирует «Bot run-loop exiting» —
                    # детали (once / stop_event) пишем DEBUG, чтобы не
                    # дублировать INFO-строку.
                    logger.debug(
                        "Run-loop terminating: once=%s stop_event=%s",
                        once,
                        self._stop_event.is_set(),
                    )
                    return
                self._wake_event.clear()
                try:
                    await asyncio.wait_for(
                        self._wake_event.wait(),
                        timeout=self._rs.poll_interval_sec,
                    )
                except asyncio.TimeoutError:
                    pass
                if self._stop_event.is_set():
                    logger.debug("Run-loop exiting after stop request")
                    return
        finally:
            logger.info("Bot run-loop exiting")
            # Shutdown-флаг ДО client.stop(): Pyrogram'овский DM-handler,
            # успевший отстрелить уже после teardown'а, увидит флаг и
            # no-op'нет вместо того, чтобы пытаться писать в закрытый
            # session_factory или дёргать httpx-клиенты, которые мы
            # сейчас будем aclose'ить.
            self._ingestion.mark_shutting_down()
            # Висящие debounce-таски DM-классификации не должны жить дольше
            # бота — иначе при reload'е RuntimeSettings (новый Bot) старые
            # таски попытаются использовать закрытый httpx-клиент.
            try:
                await self._ingestion.cancel_pending_dm_classifications()
            except Exception:
                logger.exception("cancel_pending_dm_classifications failed")
            # log_out_session() уже отключил клиент; повторный stop()
            # упадёт ConnectionError("Client is already terminated").
            # Глушим — логируем как debug.
            try:
                await self._client.stop()
            except ConnectionError:
                logger.debug("Pyrogram client already terminated; skip stop()")
            except Exception:
                logger.exception("Pyrogram client.stop() failed")
            if self._lm_embed_client is not self._lm_client:
                await self._lm_embed_client.aclose()
            await self._lm_client.aclose()

    async def ui_rerun_vacancy_pipeline(self, vacancy_id: int) -> bool:
        """Re-parse / re-classify one vacancy — vacancies detail «more» menu.

        Wraps the rerun in the same ``_current_poll_task`` slot + cycle
        hooks как обычный poll-цикл — это даёт юзеру штатный прогресс-бар
        и кнопку «остановить» в футере на время выполнения. Если уже
        идёт другой цикл, сигнализируем «busy» через возврат False —
        UI покажет toast про «не удалось перезапустить».
        """
        logger.info("UI rerun pipeline for vacancy %d", vacancy_id)
        if self._current_poll_task is not None:
            logger.info("ui_rerun: another cycle is already running, skipping")
            return False
        if self.on_cycle_start is not None:
            try: self.on_cycle_start()
            except Exception: logger.exception("on_cycle_start hook failed")
        if self.on_progress is not None:
            try: self.on_progress("rerun", f"Прогон вакансии #{vacancy_id}…", 0, 0)
            except Exception: logger.exception("on_progress hook failed")
        ok = False
        try:
            self._current_poll_task = asyncio.create_task(
                self._ingestion.rerun_pipeline_for_vacancy(vacancy_id)
            )
            try:
                ok = await self._current_poll_task
            except asyncio.CancelledError:
                logger.info("rerun pipeline for vacancy %d cancelled by user", vacancy_id)
        except Exception:
            logger.exception("rerun pipeline for vacancy %d failed", vacancy_id)
        finally:
            self._current_poll_task = None
            if self.on_cycle_end is not None:
                try: self.on_cycle_end()
                except Exception: logger.exception("on_cycle_end hook failed")
        return ok


    async def _on_raw_update(self, _client, update, _users, _chats) -> None:
        """Catch ``UpdateReadHistoryOutbox`` to mark our outgoing rows as
        read by the HR. Everything else is ignored — raw updates fire on
        every server event so the cheap-out has to come first.
        """
        if not isinstance(update, _UpdateReadHistoryOutbox):
            return
        peer = getattr(update, "peer", None)
        if not isinstance(peer, _PeerUser):
            return
        if (await self._current_mode()) is BotMode.OFF:
            return
        from datetime import datetime as _dt, timezone as _tz
        from sqlalchemy import update as _sa_update

        user_id = peer.user_id
        max_id = update.max_id
        now = _dt.now(_tz.utc)
        async with self._session_factory() as session:
            hr = await find_known_hr(session, user_id, None)
            if hr is None:
                return
            res = await session.execute(
                _sa_update(Message)
                .where(
                    Message.hr_id == hr.id,
                    Message.is_incoming.is_(False),
                    Message.tg_message_id <= max_id,
                    Message.tg_message_id.is_not(None),
                    Message.read_at.is_(None),
                )
                .values(read_at=now)
            )
            await session.commit()
            updated = res.rowcount or 0
            hr_id = hr.id
        if updated and self.on_hr_read is not None:
            try:
                self.on_hr_read(hr_id, max_id)
            except Exception:
                logger.exception("on_hr_read hook failed")

    async def _on_dm_edit(self, _client, msg) -> None:
        """Sync Telegram edits — overwrite text + mark is_edited=True."""
        if (await self._current_mode()) is BotMode.OFF:
            return
        if not msg.chat:
            return
        from sqlalchemy import update as _sa_update

        chat_id = msg.chat.id
        chat_username = getattr(msg.chat, "username", None)
        is_incoming = bool(getattr(msg, "from_user", None)
                           and not getattr(msg, "outgoing", False))
        async with self._session_factory() as session:
            hr = await find_known_hr(session, chat_id, chat_username)
            if hr is None:
                return
            res = await session.execute(
                _sa_update(Message)
                .where(
                    Message.hr_id == hr.id,
                    Message.tg_message_id == msg.id,
                    Message.is_incoming.is_(is_incoming),
                )
                .values(text=extract_dm_text(msg), is_edited=True)
            )
            await session.commit()
            updated = res.rowcount or 0
            hr_id = hr.id
        # Если это сообщение всё ещё сидит в debounce-буфере (HR отредак-
        # тировал в первые 60 сек) — обновим текст там тоже, чтобы
        # классификатор видел свежее содержимое.
        if updated and is_incoming:
            self._ingestion.update_dm_buffer_text(hr_id, msg.id, extract_text(msg))
        if updated:
            logger.debug(
                "DM edit synced: hr=%d tg_msg=%d incoming=%s",
                hr_id, msg.id, is_incoming,
            )
        if updated and self.on_new_message is not None:
            try:
                self.on_new_message(hr_id)
            except Exception:
                logger.exception("on_new_message hook failed")

    async def _on_dm_delete(self, _client, messages) -> None:
        """Sync Telegram deletes — set is_deleted=True, keep the row.

        Pyrogram delete updates are sparse: ``m.chat`` is often ``None`` for
        secret-chat / channel-less tombstones, and only ``m.id`` is
        guaranteed. We group by chat when we have it; otherwise fall back to
        a chatless sweep restricted to incoming rows. ``tg_message_id`` is
        per-chat in Telegram (NOT globally unique — two HRs routinely share
        early ids 1, 2, 3...), so the chatless branch could in principle
        flip an unrelated HR's row. We narrow to incoming because chatless
        deletes practically only happen for secret/channel sources we don't
        store anyway, and incoming-only further shrinks the collision window.
        Outgoing tombstones missed here will be reconciled the next time we
        load the chat from Telegram on app restart.

        Deleted incoming rows that were still unread also get ``read_at``
        set so the unread badge doesn't latch on a tombstone forever.
        """
        if (await self._current_mode()) is BotMode.OFF:
            return
        from datetime import datetime as _dt, timezone as _tz
        from sqlalchemy import update as _sa_update

        with_chat: dict[int, list[int]] = {}
        chatless_ids: list[int] = []
        for m in messages:
            chat = getattr(m, "chat", None)
            chat_id = getattr(chat, "id", None) if chat else getattr(m, "chat_id", None)
            if chat_id is None:
                chatless_ids.append(m.id)
            else:
                with_chat.setdefault(chat_id, []).append(m.id)
        if not with_chat and not chatless_ids:
            return

        now = _dt.now(_tz.utc)
        touched_hr_ids: set[int] = set()

        async def _flip_deleted(session, where_clauses) -> int:
            # Two updates so we can also seal read_at on incoming tombstones
            # that were still unread, without overwriting outgoing rows.
            res = await session.execute(
                _sa_update(Message)
                .where(*where_clauses)
                .values(is_deleted=True)
            )
            await session.execute(
                _sa_update(Message)
                .where(*where_clauses, Message.is_incoming, Message.read_at.is_(None))
                .values(read_at=now)
            )
            return res.rowcount or 0

        for chat_id, msg_ids in with_chat.items():
            async with self._session_factory() as session:
                # Resolve HR by chat_id; for username-only HRs we need the
                # username fallback that Pyrogram supplies on chat objects.
                chat_username = None
                for m in messages:
                    chat = getattr(m, "chat", None)
                    if chat and getattr(chat, "id", None) == chat_id:
                        chat_username = getattr(chat, "username", None)
                        break
                hr = await find_known_hr(session, chat_id, chat_username)
                if hr is None:
                    continue
                rowcount = await _flip_deleted(
                    session,
                    [Message.hr_id == hr.id, Message.tg_message_id.in_(msg_ids)],
                )
                await session.commit()
                if rowcount:
                    touched_hr_ids.add(hr.id)
                    # Если удалённое сообщение всё ещё сидит в debounce-буфере
                    # — выкинем его оттуда, чтобы не учитывать в классификации.
                    for tg_msg_id in msg_ids:
                        self._ingestion.remove_dm_buffer_msg(hr.id, tg_msg_id)

        if chatless_ids:
            async with self._session_factory() as session:
                # Chatless sweep — narrowed to incoming so we never flip an
                # outgoing row that happens to share a tg_message_id with a
                # delete from a different HR.
                hr_id_rows = (
                    await session.execute(
                        select(Message.hr_id).where(
                            Message.tg_message_id.in_(chatless_ids),
                            Message.is_incoming,
                            Message.hr_id.is_not(None),
                        )
                    )
                ).all()
                rowcount = await _flip_deleted(
                    session,
                    [
                        Message.tg_message_id.in_(chatless_ids),
                        Message.is_incoming,
                    ],
                )
                await session.commit()
                if rowcount:
                    for (hr_id,) in hr_id_rows:
                        touched_hr_ids.add(hr_id)

        if touched_hr_ids:
            logger.info(
                "DM tombstoned across %d hr(s)",
                len(touched_hr_ids),
            )
        for hr_id in touched_hr_ids:
            if self.on_new_message is not None:
                try:
                    self.on_new_message(hr_id)
                except Exception:
                    logger.exception("on_new_message hook failed")

    async def _on_dm_outgoing(self, _client, msg) -> None:
        """Capture messages the user typed from another TG client (phone /
        desktop) so the in-app chat stays in sync. Mirrors the OFF-mode
        gating of the incoming handler — OFF silences both directions.

        Resolves HR by recipient's user_id (msg.chat.id for private chats).
        Dedup via the UNIQUE constraint — when we sent the message ourselves
        from this app the row already exists with the same tg_message_id.
        """
        if (await self._current_mode()) is BotMode.OFF:
            return
        if not msg.chat:
            return

        recipient_id = msg.chat.id
        recipient_username = getattr(msg.chat, "username", None)
        async with self._session_factory() as session:
            hr = await find_known_hr(session, recipient_id, recipient_username)
            if hr is None:
                return
            hr_id_for_media = hr.id
            # Если эта же исходящая уже вставлена нашим send_to_hr_chat /
            # send_to_hr_media (UNIQUE на (hr_id, tg_message_id, is_incoming)),
            # повторно качать медиа и копаться в БД незачем — мы получили
            # echo собственного отправленного сообщения. Без этой проверки
            # download_media гонится с shutil.copy2 за один и тот же путь
            # и оставляет рваный файл в кэше.
            existing = (
                await session.scalars(
                    select(Message).where(
                        Message.hr_id == hr_id_for_media,
                        Message.tg_message_id == msg.id,
                        Message.is_incoming.is_(False),
                    )
                )
            ).first()
            if existing is not None:
                # Echo собственного Bot.send-а: row уже была вписана при
                # отправке cover-letter'а, повторно её писать не надо, но
                # UI ещё не уведомлён — chat должен обновиться синхронно
                # с прилётом echo из Telegram.
                if self.on_new_message is not None:
                    try:
                        self.on_new_message(hr_id_for_media)
                    except Exception:
                        logger.exception("on_new_message hook failed")
                return
        media_kind, media_name = media._classify_media(msg)
        media_path = (
            await media._download_media(self._client, msg, hr_id_for_media)
            if media_kind is not None else None
        )
        async with self._session_factory() as session:
            hr = await find_known_hr(session, recipient_id, recipient_username)
            if hr is None:
                return
            try:
                session.add(Message(
                    is_incoming=False,
                    hr_id=hr.id,
                    text=extract_dm_text(msg),
                    tg_message_id=msg.id,
                    sent_at=msg.date,
                    media_kind=media_kind,
                    media_path=media_path,
                    media_name=media_name,
                ))
                await session.commit()
            except IntegrityError:
                logger.debug(
                    "Outgoing DM dedup: hr=%d tg_msg=%d already saved",
                    hr.id, msg.id,
                )
                return  # already saved (e.g. via send_to_hr_chat)
            except Exception:
                logger.exception(
                    "outgoing DM persistence failed",
                    extra={"hr_id": hr.id, "tg_message_id": msg.id},
                )
                return
            hr_id = hr.id
        if self.on_new_message is not None:
            try:
                self.on_new_message(hr_id)
            except Exception:
                logger.exception("on_new_message hook failed")

    async def _on_dm(self, _client, msg) -> None:
        # Off mode silences everything, including reading HR replies.
        if (await self._current_mode()) is BotMode.OFF:
            return
        await process_dm(
            msg,
            self._lm_client,
            self._lm_chat_model,
            self._session_factory,
            client=self._client,
            schedule_classification=self._ingestion.schedule_dm_classification,
        )
        # `on_vacancies_changed` НЕ пушим здесь — статус вакансии флипнется
        # debounce-таском через ~60с после burst'а (см. IngestionPipeline.
        # _run_debounced_classify), он же сам пушнёт сигнал. До того статус
        # не менялся, любой ранний refetch вкладки «Вакансии» отдал бы
        # тот же набор статусов и зря грузил бы БД/UI.
        # Push a UI signal so an open Contacts/HR chat with this HR can
        # refresh in real time without polling. We look up hr_id after
        # process_dm rather than threading a callback through it — keeps
        # process_dm's signature clean and avoids touching unrelated flows.
        if self.on_new_message is None:
            return
        if not msg.from_user:
            return
        try:
            async with self._session_factory() as session:
                hr = await find_known_hr(
                    session,
                    msg.from_user.id,
                    msg.from_user.username,
                )
            if hr is not None:
                self.on_new_message(hr.id)
        except Exception:
            logger.exception("on_new_message hook failed")

    async def _persist_session_if_changed(self) -> None:
        """After client.start(), export the (possibly fresh) session_string and
        write it back to runtime_settings if it differs from what we loaded.

        Covers two cases:
        * first interactive login (file-based session) — promotes to in-memory
          string on next run;
        * Telegram DC migrations / auth-key rotations — keeps the persisted
          copy in sync.
        """
        try:
            new_str = await self._client.export_session_string()
        except Exception:
            logger.exception("export_session_string failed; not persisting")
            return
        tg = self._rs.tg
        if tg is None:
            return
        if new_str == (tg.session_string or ""):
            return
        try:
            await self._rs.set_tg(
                api_id=tg.api_id,
                api_hash=tg.api_hash,
                phone=tg.phone,
                password=tg.password,
                session_string=new_str,
            )
            logger.info("persisted refreshed Telegram session_string")
        except Exception:
            logger.exception("persist session_string failed")

    async def poll_channel_now(self, channel_id):
        return await channels.poll_channel_now(self, channel_id)

    async def reset_channel_cursor(self, channel_id):
        return await channels.reset_channel_cursor(self, channel_id)

    async def delete_channel(self, channel_id):
        return await channels.delete_channel(self, channel_id)

    async def add_channel(self, username):
        return await channels.add_channel(self, username)

    def cancel_current_poll(self):
        return channels.cancel_current_poll(self)

    async def force_poll_once(self):
        return await channels.force_poll_once(self)

    async def mark_hr_chat_read(self, hr_id):
        return await chat.mark_hr_chat_read(self, hr_id)

    async def send_to_hr_chat(self, hr_id, text):
        return await chat.send_to_hr_chat(self, hr_id, text)

    async def send_to_hr_media(self, hr_id, file_path):
        return await chat.send_to_hr_media(self, hr_id, file_path)

    async def ui_send_vacancy_application(self, vacancy_id):
        return await send.ui_send_vacancy_application(self, vacancy_id)

    async def send(self, hr, text, attachment=None, vacancy_id=None, *, force=False):
        return await send.send(self, hr, text, attachment, vacancy_id, force=force)
