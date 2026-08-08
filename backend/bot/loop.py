"""Жизненный цикл соединения: режим работы, главный цикл, выход из сеанса."""

import logging
import asyncio

from adapters import telegram
from backend.flows.dm import catch_up_missed_dms
from backend.models import BotMode

logger = logging.getLogger(__name__)


async def log_out_session(bot) -> None:
    """Revoke server-side TG session via DROP_AUTH and exit the run loop.

    Pyrogram's log_out() also disconnects the client and removes the
    local session file. Errors are logged but don't propagate — the
    caller still wants the bot to stop and the local creds cleared.
    """
    logger.info("TG log_out requested")
    try:
        await bot._client.log_out()
    except Exception:
        logger.exception("log_out RPC failed; proceeding to stop bot")
    bot._stop_event.set()
    bot._wake_event.set()


async def _current_mode(bot) -> BotMode:
    try:
        return await bot._rs.get_mode()
    except Exception:
        logger.exception("get_mode failed; falling back to Off")
        return BotMode.OFF


async def run(bot, *, once: bool = False) -> None:
    if bot._dry_run:
        logger.warning("DRY-RUN mode: outgoing TG messages will NOT be sent")
    # Синкаем dev-safety lock из БД-настройки в module-level guard
    # adapters/telegram.send_dm. Авторитет — rs.send_locked; константа
    # — defence-in-depth на случай если Bot.send забудет проверить.
    telegram.SEND_LOCKED = bot._rs.send_locked
    if telegram.SEND_LOCKED:
        logger.warning(
            "SEND_LOCKED=True: outgoing DM will be simulated, not sent"
        )
    await bot._client.start()
    # ``bot._loop`` ставим ПОСЛЕ client.start() — это и метка
    # «бот готов принимать kick/cancel из Qt-треда», и сам loop
    # для thread-safe методов. До этого момента kick/cancel/
    # request_stop fallback'ятся на прямой .set() (безопасно: Event
    # ещё не имеет ожидателей; а poll-task ещё не создан, так что
    # и cancel'ить нечего).
    bot._loop = asyncio.get_running_loop()
    from backend.runtime_settings import _mask_phone
    logger.info(
        "Telegram client connected (phone=%s)",
        _mask_phone(bot._rs.tg.phone if bot._rs.tg else None),
    )
    await _persist_session_if_changed(bot)
    try:
        # Re-parse any vacancies that were ingested but never finished
        # the LLM pipeline (previous process crashed mid-parse). Runs
        # before polling so the UI doesn't briefly show empty rows
        # alongside fresh ones, and so a long-stuck orphan eventually
        # gets unstuck even if its source channel never re-posts the
        # same message.
        try:
            await bot._ingestion.recover_orphan_vacancies()
        except Exception:
            logger.exception("orphan recovery failed")
        # OFF is a full stop — no DM catch-up, no LLM classification,
        # no polling. Catch-up runs once on every transition into an
        # active mode (including the initial transition from the seeded
        # OFF state at process start), so a fresh start in DM Only / Full
        # back-fills immediately and so does toggling out of OFF later.
        prev_mode = BotMode.OFF
        while True:
            mode = await _current_mode(bot)
            # Transition в OFF: гасим debounce-таймеры pending'овых
            # классификаций. Накопленные тексты пропадают, но сами
            # сообщения уже в БД — юзеру нужно будет переклассифицировать
            # вручную через UI если нужно.
            if mode is BotMode.OFF and prev_mode is not BotMode.OFF:
                logger.info("Transition into OFF; draining DM debouncers")
                await bot._ingestion.cancel_pending_dm_classifications(drain=True)
            if mode is not BotMode.OFF and prev_mode is BotMode.OFF:
                logger.info(
                    "Transition into active mode (%s); running DM catch-up",
                    mode.value,
                )
                try:
                    await catch_up_missed_dms(
                        bot._client,
                        bot._lm_client,
                        bot._lm_chat_model,
                        bot._session_factory,
                        backfill_limit=bot._rs.dm_backfill_limit,
                        on_message_persisted=bot.on_new_message,
                        on_vacancies_changed=bot.on_vacancies_changed,
                        schedule_classification=bot._ingestion.schedule_dm_classification,
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
                    await bot._ingestion.check_ghosting_timeouts()
                except Exception:
                    logger.exception("ghosting timer tick failed")
            # Channel polling and outbound applications are Full-only.
            # DM Only and Off both skip ingestion (DM Only still reacts
            # to incoming HR messages via the registered MessageHandler).
            if mode is BotMode.FULL and bot._current_poll_task is None:
                # Гард от клоббера: если ручной `poll_channel_now` или
                # `force_poll_once` сейчас держит слот, не перетираем
                # его новой задачей — иначе обе крутятся параллельно
                # и гонят embedding-кэш и курсоры каналов.
                if bot.on_cycle_start is not None:
                    try: bot.on_cycle_start()
                    except Exception: logger.exception("on_cycle_start hook failed")
                try:
                    bot._current_poll_task = asyncio.create_task(
                        bot._ingestion.poll_active_channels()
                    )
                    try:
                        await bot._current_poll_task
                    except asyncio.CancelledError:
                        logger.info("poll cycle cancelled by user")
                except Exception:
                    logger.exception("poll cycle failed")
                finally:
                    bot._current_poll_task = None
                    if bot.on_cycle_end is not None:
                        try: bot.on_cycle_end()
                        except Exception: logger.exception("on_cycle_end hook failed")
            prev_mode = mode
            if once or bot._stop_event.is_set():
                # finally-блок ниже логирует «Bot run-loop exiting» —
                # детали (once / stop_event) пишем DEBUG, чтобы не
                # дублировать INFO-строку.
                logger.debug(
                    "Run-loop terminating: once=%s stop_event=%s",
                    once,
                    bot._stop_event.is_set(),
                )
                return
            bot._wake_event.clear()
            try:
                await asyncio.wait_for(
                    bot._wake_event.wait(),
                    timeout=bot._rs.poll_interval_sec,
                )
            except asyncio.TimeoutError:
                pass
            if bot._stop_event.is_set():
                logger.debug("Run-loop exiting after stop request")
                return
    finally:
        logger.info("Bot run-loop exiting")
        # Shutdown-флаг ДО client.stop(): Pyrogram'овский DM-handler,
        # успевший отстрелить уже после teardown'а, увидит флаг и
        # no-op'нет вместо того, чтобы пытаться писать в закрытый
        # session_factory или дёргать httpx-клиенты, которые мы
        # сейчас будем aclose'ить.
        bot._ingestion.mark_shutting_down()
        # Висящие debounce-таски DM-классификации не должны жить дольше
        # бота — иначе при reload'е RuntimeSettings (новый Bot) старые
        # таски попытаются использовать закрытый httpx-клиент.
        try:
            await bot._ingestion.cancel_pending_dm_classifications()
        except Exception:
            logger.exception("cancel_pending_dm_classifications failed")
        # log_out_session() уже отключил клиент; повторный stop()
        # упадёт ConnectionError("Client is already terminated").
        # Глушим — логируем как debug.
        try:
            await bot._client.stop()
        except ConnectionError:
            logger.debug("Pyrogram client already terminated; skip stop()")
        except Exception:
            logger.exception("Pyrogram client.stop() failed")
        if bot._lm_embed_client is not bot._lm_client:
            await bot._lm_embed_client.aclose()
        await bot._lm_client.aclose()


async def _persist_session_if_changed(bot) -> None:
    """After client.start(), export the (possibly fresh) session_string and
    write it back to runtime_settings if it differs from what we loaded.

    Covers two cases:
    * first interactive login (file-based session) — promotes to in-memory
      string on next run;
    * Telegram DC migrations / auth-key rotations — keeps the persisted
      copy in sync.
    """
    try:
        new_str = await bot._client.export_session_string()
    except Exception:
        logger.exception("export_session_string failed; not persisting")
        return
    tg = bot._rs.tg
    if tg is None:
        return
    if new_str == (tg.session_string or ""):
        return
    try:
        await bot._rs.set_tg(
            api_id=tg.api_id,
            api_hash=tg.api_hash,
            phone=tg.phone,
            password=tg.password,
            session_string=new_str,
        )
        logger.info("persisted refreshed Telegram session_string")
    except Exception:
        logger.exception("persist session_string failed")
