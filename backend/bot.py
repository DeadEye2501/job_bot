"""Bot class — long-running pyrogram client + ingestion loop.

Entry point for the application is at the project root: ``main.py``.
This module only defines the ``Bot`` class; ``main.py`` is what wires
schema-migration / wizard / Bot construction together.
"""

import asyncio
import logging
import mimetypes
import shutil
from pathlib import Path
from typing import Literal

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
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from adapters import lm_studio, telegram
from config import get_data_dir
from backend import repository
from backend.domain import should_apply_status
from backend.flows import IngestionPipeline, catch_up_missed_dms, process_dm
from backend.models import HR, BotMode, Message, Vacancy, VacancyStatus
from backend.runtime_settings import RuntimeSettings


logger = logging.getLogger(__name__)


# Where downloaded media gets cached. Lives next to the SQLite DB under
# the OS user-data dir (``%APPDATA%/JobBot/media`` on Windows) so the .exe
# distribution doesn't end up writing under Program Files.
MEDIA_DIR = get_data_dir() / "media"
PHOTO_EXTS = {".png", ".jpg", ".jpeg", ".webp"}  # GIFs go via send_document → preserved as animation

# User-facing caps на upload. Telegram regular doc-limit ≈ 2 GB, но без
# прогресс-индикатора и cancel'а файлы такого размера повесят UI; эти
# границы — практический разумный максимум для job-bot use-case (резюме,
# скриншоты, портфолио). Превышение → внятный RuntimeError, ловим в bridge.
PHOTO_SIZE_LIMIT = 10 * 1024 * 1024
DOCUMENT_SIZE_LIMIT = 50 * 1024 * 1024


def _looks_like_photo(path: Path) -> bool:
    """Эвристика для выбора send_photo vs send_document. Pyrogram (и сам
    Telegram) принимают в send_photo только JPEG/PNG/WEBP — поэтому
    photo-ветка ЖЁСТКО ограничена этими расширениями. HEIC/HEIF/BMP/TIFF
    и т.п. — изображения по MIME, но send_photo на них падает на сервере;
    их (как и GIF) уводим в send_document, чтобы файл хотя бы дошёл.
    MIME-проверка тут — защита от переименованного .exe-в-.jpg: даже
    при правильном расширении из PHOTO_EXTS, если mimetypes не распознал
    image/*, отправляем документом."""
    suffix = path.suffix.lower()
    if suffix not in PHOTO_EXTS:
        return False
    mime, _ = mimetypes.guess_type(str(path))
    return bool(mime and mime.startswith("image/"))


def _classify_media(msg) -> tuple[str | None, str | None]:
    """Return ``(media_kind, media_name)`` for a Pyrogram DM. We persist only
    photos and documents; everything else (sticker / video / voice / etc.)
    falls back to a text bubble with the placeholder set in ``extract_dm_text``.
    """
    if getattr(msg, "photo", None):
        return "photo", None
    doc = getattr(msg, "document", None)
    if doc is not None:
        return "document", getattr(doc, "file_name", None)
    return None, None


def _media_cache_path(hr_id: int, tg_message_id: int, ext: str) -> Path:
    """Deterministic cache path so duplicate-row races (handler vs explicit
    send) collide on the same file rather than producing orphans.
    """
    return MEDIA_DIR / str(hr_id) / f"{tg_message_id}{ext}"


def _media_path_for_db(path) -> str:
    """Convert a media-cache absolute path into a posix string relative to
    ``MEDIA_DIR`` for storage. Falls back to the absolute posix form for any
    path outside MEDIA_DIR (shouldn't happen — every cache write goes
    through ``_media_cache_path`` — but kept defensive).
    """
    p = Path(path).resolve()
    try:
        return p.relative_to(MEDIA_DIR.resolve()).as_posix()
    except ValueError:
        return p.as_posix()


async def _download_media(client, msg, hr_id: int) -> str | None:
    """Download a photo or document to ``media/{hr_id}/{tg_message_id}{ext}``.
    Returns the project-relative posix path or ``None`` if there's no
    supported media on the message. Skips re-download if the file already
    exists (handler/manual-send race writes the same path either way).
    """
    kind, _ = _classify_media(msg)
    if kind is None:
        return None
    if kind == "photo":
        ext = ".jpg"  # Pyrogram delivers photos as JPEGs
    else:
        ext = Path(getattr(msg.document, "file_name", "") or "").suffix or ".bin"
    out = _media_cache_path(hr_id, msg.id, ext)
    if out.exists():
        return _media_path_for_db(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        path = await client.download_media(msg, file_name=str(out))
    except Exception:
        logger.exception(
            "media download failed",
            extra={"hr_id": hr_id, "tg_message_id": msg.id, "kind": kind},
        )
        return None
    if not path:
        return None
    return _media_path_for_db(path)


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
            if _shares_provider(runtime_settings.chat, runtime_settings.embed)
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
        self._client.add_handler(
            DeletedMessagesHandler(self._on_dm_delete, filters.private)
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

    async def poll_channel_now(
        self, channel_id: int
    ) -> Literal["ok", "busy", "missing", "cancelled", "error"]:
        """UI «Прогнать сейчас» — single-channel manual poll.

        Wraps the same `_current_poll_task` slot + `on_cycle_start/end`
        hooks as the global cycle so the bottom-bar progress indicator,
        stop-button (`cancel_current_poll`), и all other "идёт цикл"
        UI affordances работают одинаково для ручного single-channel
        прогона.

        Returns a status string so the bridge can give a tailored toast
        for each outcome instead of one generic «не найден» error:
        - "ok": cycle ran end-to-end.
        - "busy": another cycle was already in flight (skip).
        - "missing": channel row не существует / без @username.
        - "cancelled": user clicked stop mid-poll.
        - "error": unexpected exception inside `poll_one_channel`.
        """
        if self._current_poll_task is not None:
            logger.info(
                "poll_channel_now: another cycle is running, skipping (channel_id=%d)",
                channel_id,
            )
            return "busy"
        if self.on_cycle_start is not None:
            try: self.on_cycle_start()
            except Exception: logger.exception("on_cycle_start hook failed")
        status: Literal["ok", "missing", "cancelled", "error"] = "ok"
        try:
            self._current_poll_task = asyncio.create_task(
                self._ingestion.poll_one_channel(channel_id)
            )
            try:
                ok = await self._current_poll_task
                if not ok:
                    status = "missing"
            except asyncio.CancelledError:
                logger.info(
                    "manual poll for channel %d cancelled by user", channel_id
                )
                status = "cancelled"
        except Exception:
            logger.exception("manual single-channel poll failed (channel_id=%d)", channel_id)
            status = "error"
        finally:
            self._current_poll_task = None
            if self.on_cycle_end is not None:
                try: self.on_cycle_end()
                except Exception: logger.exception("on_cycle_end hook failed")
        return status

    async def reset_channel_cursor(self, channel_id: int) -> bool:
        """UI «Сбросить курсор» — clears last_processed_msg_id."""
        async with self._session_factory() as session:
            async with session.begin():
                return await repository.reset_channel_cursor(session, channel_id)

    async def delete_channel(self, channel_id: int) -> int | None:
        """UI «Удалить канал» — severs vacancy FKs and deletes the row.
        Returns count of detached vacancies, or None if channel missing.
        """
        async with self._session_factory() as session:
            async with session.begin():
                return await repository.delete_channel(session, channel_id)

    async def add_channel(
        self, username: str
    ) -> tuple[int | None, Literal["created", "exists", "invalid"]]:
        """Validate against Telegram and insert a TelegramChannel.

        Returns a status tuple:
        - ``(id, "exists")`` — row уже была; UI выбирает её и тостит «уже добавлен».
        - ``(id, "created")`` — новая строка с подгруженными title/avatar.
        - ``(None, "invalid")`` — Telegram не знает такой канал; ничего
          не пишем в БД, чтобы пользователь не накапливал зомби-ряды без
          title/avatar после опечаток.

        Метаданные тянем ДО инсёрта одним `get_chat`-вызовом — он же
        выступает валидатором существования.
        """
        async with self._session_factory() as session:
            existing = await repository.find_channel_by_username(session, username)
            if existing is not None:
                return existing.id, "exists"

        from backend.helpers import fetch_telegram_avatar
        try:
            chat = await self._client.get_chat(username)
        except Exception as e:
            logger.warning(
                "add_channel: get_chat(%s) failed: %s: %s",
                username, type(e).__name__, e,
            )
            return None, "invalid"
        if chat is None:
            return None, "invalid"

        title = getattr(chat, "title", None)
        avatar = (
            await fetch_telegram_avatar(self._client, chat)
            if getattr(chat, "photo", None) is not None
            else None
        )

        async with self._session_factory() as session:
            async with session.begin():
                # Race-guard: ещё одна вкладка/процесс могла успеть вставить
                # за время `get_chat` — повторно проверяем дубль.
                existing = await repository.find_channel_by_username(session, username)
                if existing is not None:
                    return existing.id, "exists"
                from backend.models import TelegramChannel
                ch = TelegramChannel(
                    username=username.lower(),
                    title=title,
                    is_active=True,
                    avatar=avatar,
                )
                session.add(ch)
                await session.flush()
                channel_id = ch.id
        return channel_id, "created"

    def cancel_current_poll(self) -> None:
        """Cancel an in-flight poll cycle without stopping the whole bot.

        Thread-safe: см. ``kick``. Task.cancel() из чужого треда мутирует
        внутреннее состояние Task'а и пытается loop.call_soon — обязан
        идти через call_soon_threadsafe.
        """
        task = self._current_poll_task
        if task is None or task.done():
            return
        logger.info("Cancel current poll requested")
        loop = self._loop
        if loop is not None and not loop.is_closed():
            loop.call_soon_threadsafe(task.cancel)
        else:
            task.cancel()

    async def force_poll_once(self) -> None:
        """Manual one-shot poll, fired regardless of bot_state.mode. Used by
        the refresh button so the user always sees something happen.

        No-op if a poll cycle is already running (UI's stop button takes
        precedence) — two concurrent cycles would race on the embedding
        cache and the channel cursor.
        """
        if self._current_poll_task is not None:
            logger.info("force_poll_once: another cycle is already running, skipping")
            return
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
                logger.info("forced poll cycle cancelled by user")
        except Exception:
            logger.exception("forced poll cycle failed")
        finally:
            self._current_poll_task = None
            if self.on_cycle_end is not None:
                try: self.on_cycle_end()
                except Exception: logger.exception("on_cycle_end hook failed")

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
                    logger.info("Transition into OFF; cancelling pending DM debouncers")
                    await self._ingestion.cancel_pending_dm_classifications()
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
        """Re-parse / re-classify one vacancy — vacancies detail «more» menu."""
        logger.info("UI rerun pipeline for vacancy %d", vacancy_id)
        return await self._ingestion.rerun_pipeline_for_vacancy(vacancy_id)

    async def ui_send_vacancy_application(self, vacancy_id: int) -> tuple[bool, str]:
        """Manual cover-letter send — vacancy detail «more» menu, кнопка
        «Отправить отклик». Возвращает (ok, reason) — UI использует reason
        для понятного toast'а (что именно не сработало)."""
        logger.info("UI send application for vacancy %d", vacancy_id)
        return await self._ingestion.send_application_for_vacancy(vacancy_id)

    async def send(
        self,
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
        if (await self._current_mode()) is BotMode.OFF:
            logger.warning(
                "Bot.send: BotMode.OFF, suppressed send to %s (vacancy=%s)",
                target, vacancy_id,
            )
            return False
        # Blacklist: HR мог попасть туда между парсингом вакансии и отправкой
        # отклика (особенно для авто-flow, где между парсингом и send'ом
        # может пройти время на LLM-генерацию). Зеркалит проверку из
        # send_to_hr_chat / send_to_hr_media.
        async with self._session_factory() as session:
            from backend.repository import _hr_blacklist_value
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
        suppressed = self._dry_run or telegram.SEND_LOCKED
        tg_msg_id: int | None = None
        if suppressed:
            tag = "[DRY-RUN]" if self._dry_run else "[SEND_LOCKED]"
            logger.warning(
                "%s would have sent DM to %s (vacancy=%s, %d chars, attachment=%s)",
                tag, target, vacancy_id, len(text), attachment,
            )
        else:
            logger.info(
                "Sending DM to hr %s (vacancy=%s, %d chars)",
                target, vacancy_id, len(text),
            )
            tg_msg_id = await telegram.send_dm(
                self._client, target, text, attachment
            )
        # С этого момента сообщение УШЛО к HR (или сэмулировано). Если
        # коммит ниже упадёт — сообщение в Telegram реальное, а Message-row
        # в БД нет. Чтобы повторное «Отправить отклик» НЕ отправило DM
        # ещё раз, делаем fallback-flip status=APPLIED отдельной тонкой
        # транзакцией: пусть аудит-row потерян, но re-send отбивается
        # стандартной already_applied-проверкой в send_application_for_vacancy.
        try:
            async with self._session_factory() as session:
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
                        v.status = VacancyStatus.APPLIED
                        applied_now = True
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
                    async with self._session_factory() as session:
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
        return True

    async def mark_hr_chat_read(self, hr_id: int) -> int:
        """Mark all incoming HR messages as read in the DB AND in Telegram.

        OFF mode short-circuits: nothing is written, nothing is pinged.
        Returns the number of DB rows updated. The Pyrogram call propagates
        the read receipt to the user's other clients (phone, desktop). When
        the HR has no telegram_user_id we still update the DB but skip the
        Pyrogram side — the Telegram-side read receipt will arrive later
        through ``UpdateReadHistoryInbox`` when the user opens it elsewhere.
        """
        if (await self._current_mode()) is BotMode.OFF:
            return 0
        from sqlalchemy import update as _sa_update
        from datetime import datetime as _dt, timezone as _tz
        now = _dt.now(_tz.utc)
        async with self._session_factory() as session:
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
                await self._client.read_chat_history(target)
            except Exception:
                logger.exception(
                    "read_chat_history failed for hr %d", hr_id,
                    extra={"hr_id": hr_id},
                )
        if updated > 0:
            logger.debug("Marked %d msgs read for hr %d", updated, hr_id)
        return updated

    async def send_to_hr_chat(self, hr_id: int, text: str) -> Message:
        """Send a chat message to an HR from the Contacts/HR pane (slice 5).

        Resolves the Telegram target as ``telegram_user_id`` (preferred —
        works even if the HR's username changed) with ``telegram_username``
        as fallback. Returns the persisted Message row.

        Raises ``RuntimeError`` for any failure mode the UI can usefully
        surface (DRY-RUN / SEND_LOCKED suppression, missing HR, missing
        Telegram contact, Pyrogram errors). Bridge converts the message
        into a toast.
        """
        if (await self._current_mode()) is BotMode.OFF:
            raise RuntimeError("Бот выключен. Включите DM Only или Full.")
        if self._dry_run:
            raise RuntimeError("Отправка отключена: тестовый режим.")
        if telegram.SEND_LOCKED:
            raise RuntimeError("Отправка отключена: защита от случайной отправки.")

        clean = (text or "").strip()
        if not clean:
            raise RuntimeError("Пустое сообщение.")

        async with self._session_factory() as session:
            hr = await session.get(HR, hr_id)
            if hr is None:
                raise RuntimeError(f"HR id={hr_id} не найден.")
            target = hr.telegram_user_id or hr.telegram_username
            from backend.repository import _hr_blacklist_value
            bl_value = await _hr_blacklist_value(session, hr)
        if target is None:
            raise RuntimeError(
                "У HR нет ни telegram_user_id, ни @username — нечем отправить."
            )
        if bl_value:
            raise RuntimeError(
                f"HR в blacklist ({bl_value}). Сначала уберите из blacklist."
            )

        pyro_msg = await self._client.send_message(target, clean)
        logger.info(
            "Chat DM sent to hr %d (tg_msg=%d, %d chars)",
            hr_id, pyro_msg.id, len(clean),
        )

        # _on_dm_outgoing dispatches on the same client and may win the race —
        # it'll persist the row first and our INSERT then trips the
        # (hr_id, tg_message_id, is_incoming=False) UNIQUE. Treat that as
        # success and return the existing row.
        from sqlalchemy.exc import IntegrityError
        async with self._session_factory() as session:
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
            await session.refresh(row)
        return row

    async def send_to_hr_media(self, hr_id: int, file_path: str) -> Message:
        """Send a photo or document to the HR. Mirrors ``send_to_hr_chat``'s
        guards and race handling. The file is also copied into our ``media/``
        cache so the chat UI can render it without re-downloading from
        Telegram.
        """
        if (await self._current_mode()) is BotMode.OFF:
            raise RuntimeError("Бот выключен. Включите DM Only или Full.")
        if self._dry_run:
            raise RuntimeError("Отправка отключена: тестовый режим.")
        if telegram.SEND_LOCKED:
            raise RuntimeError("Отправка отключена: защита от случайной отправки.")

        src = Path(file_path)
        if not src.exists() or not src.is_file():
            raise RuntimeError(f"Файл не найден: {file_path}")

        async with self._session_factory() as session:
            hr = await session.get(HR, hr_id)
            if hr is None:
                raise RuntimeError(f"HR id={hr_id} не найден.")
            target = hr.telegram_user_id or hr.telegram_username
            from backend.repository import _hr_blacklist_value
            bl_value = await _hr_blacklist_value(session, hr)
        if target is None:
            raise RuntimeError(
                "У HR нет ни telegram_user_id, ни @username — нечем отправить."
            )
        if bl_value:
            raise RuntimeError(
                f"HR в blacklist ({bl_value}). Сначала уберите из blacklist."
            )

        as_photo = _looks_like_photo(src)
        try:
            size = src.stat().st_size
        except OSError as e:
            raise RuntimeError(f"Не удалось прочитать файл: {e}")
        cap = PHOTO_SIZE_LIMIT if as_photo else DOCUMENT_SIZE_LIMIT
        if size > cap:
            mb_cap = cap // (1024 * 1024)
            kind_ru = "фото" if as_photo else "документ"
            raise RuntimeError(
                f"Слишком большой {kind_ru}: {size / (1024*1024):.1f} MB "
                f"> лимит {mb_cap} MB."
            )
        if as_photo:
            pyro_msg = await self._client.send_photo(target, str(src))
        else:
            pyro_msg = await self._client.send_document(target, str(src))
        logger.info(
            "Chat media sent to hr %d (tg_msg=%d, kind=%s, name=%s)",
            hr_id,
            pyro_msg.id,
            "photo" if as_photo else "document",
            src.name,
        )

        # Copy into our media cache. Path matches what `_on_dm_outgoing`'s
        # `_download_media` would have written, so the racing handler that
        # downloads the same message can find the already-existing file
        # instead of re-fetching it from Telegram.
        ext = ".jpg" if as_photo else (src.suffix or ".bin")
        dest = _media_cache_path(hr_id, pyro_msg.id, ext)
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(src, dest)
            media_path = _media_path_for_db(dest)
        except Exception:
            logger.exception(
                "media cache copy failed",
                extra={"hr_id": hr_id, "src": str(src), "dest": str(dest)},
            )
            media_path = None
        media_kind = "photo" if as_photo else "document"
        media_name = None if as_photo else src.name

        from sqlalchemy.exc import IntegrityError
        async with self._session_factory() as session:
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
            await session.refresh(row)
        return row

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
        from backend.repository import find_known_hr

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
        from backend.helpers import extract_dm_text
        from backend.repository import find_known_hr

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
        from backend.repository import find_known_hr

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
        from sqlalchemy.exc import IntegrityError
        from backend.helpers import extract_dm_text
        from backend.repository import find_known_hr

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
                return
        media_kind, media_name = _classify_media(msg)
        media_path = (
            await _download_media(self._client, msg, hr_id_for_media)
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
            from backend.repository import find_known_hr
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
