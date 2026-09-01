"""Жизненный цикл соединения: режим работы, главный цикл, выход из сеанса."""

import logging
from dataclasses import replace
import asyncio

from adapters import telegram
from backend.bot import slot
from backend.flows.dm_backfill import catch_up_missed_dms
from backend.repository.bot_mode import read_mode
from backend.models import BotMode

logger = logging.getLogger(__name__)


async def log_out_session(bot) -> None:
    """Отозвать ключ на серверах Telegram и вывести цикл из работы.

    Беда отзыва уходит наружу: не отозванный ключ, выданный за отозванный,
    оставляет человека с живым сеансом, о котором он думает, что вышел.
    Решает, что с этим сказать окну, зовущий.

    Остановка идёт в любом случае — нажали «выйти», и работать боту больше
    нечем: своё соединение Pyrogram при удавшемся отзыве закрывает сам, а при
    сорвавшемся оно ведёт в учётную запись, из которой человек уходит.
    """
    logger.info("TG log_out requested")
    try:
        await bot.client.log_out()
    finally:
        bot.stop_event.set()
        bot.wake_event.set()


async def current_mode(bot) -> BotMode:
    try:
        async with bot.session_factory() as session:
            return await read_mode(session)
    except Exception:
        logger.exception("read_mode failed; falling back to Off")
        return BotMode.OFF


async def _warm_peer_cache(bot) -> None:
    """Прогреть кэш пиров; сорвавшийся прогрев подъёма не отменяет.

    Чем греют, знает адаптер Pyrogram. Здесь решается только судьба неудачи:
    без прогрева приложение работает так же, как работало до него, и ронять
    из-за этого подъём нечем — а без соединения не работает вовсе ничего.
    """
    try:
        await telegram.warm_peer_cache(bot.client)
    except Exception:
        logger.exception("peer cache warm-up failed")


async def _connect(bot) -> None:
    """Поднять соединение и объявить бота готовым к обращениям из окна."""
    # Синкаем галку «Симуляция отправки» из БД-настройки в module-level guard
    # adapters/telegram.send_dm. Авторитет — rs.send_locked; константа
    # — defence-in-depth на случай если Bot.send забудет проверить.
    telegram.SEND_LOCKED = bot.rs.send_locked
    if telegram.SEND_LOCKED:
        logger.warning(
            "SEND_LOCKED=True: outgoing DM will be simulated, not sent"
        )
    await bot.client.start()
    # Строка сеанса записывается до прогрева: прогрев идёт по сети и длится, а
    # свежая строка после первого входа дорога — оборвись приложение в эти
    # секунды, человек входил бы по коду заново.
    await persist_session_if_changed(bot)
    # Прогрев — до объявления готовности: окно, узнавшее о готовом боте, шлёт
    # письма сразу, а по холодному кэшу они падают.
    await _warm_peer_cache(bot)
    # ``bot.loop`` ставим ПОСЛЕ client.start() — это и метка
    # «бот готов принимать kick/cancel из потока окна», и сам loop
    # для thread-safe методов. До этого момента kick/cancel/
    # request_stop fallback'ятся на прямой .set() (безопасно: Event
    # ещё не имеет ожидателей; а poll-task ещё не создан, так что
    # и cancel'ить нечего).
    bot.loop = asyncio.get_running_loop()
    from backend.runtime_settings import mask_phone
    logger.info(
        "Telegram client connected (phone=%s)",
        mask_phone(bot.rs.tg.phone if bot.rs.tg else None),
    )


async def _on_mode_switch(bot, prev_mode: BotMode, mode: BotMode) -> None:
    """Что делается один раз на переходе между режимами, а не каждый оборот."""
    # Уход в OFF гасит таймеры отложенного разбора, но накопленное не
    # выбрасывает: `drain=True` разбирает его напоследок — иначе пачка писем,
    # застигнутая выключением, осталась бы без вердикта до ручного прогона.
    if mode is BotMode.OFF and prev_mode is not BotMode.OFF:
        logger.info("Transition into OFF; draining DM debouncers")
        await bot.ingestion.cancel_pending_dm_classifications(drain=True)
    if mode is not BotMode.OFF and prev_mode is BotMode.OFF:
        logger.info(
            "Transition into active mode (%s); running DM catch-up",
            mode.value,
        )
        _spawn_catch_up(bot)


def _spawn_catch_up(bot) -> None:
    """Пустить догон переписки задачей.

    Задачей, а не зовом: догон идёт по всем известным собеседникам и длится, а
    стоит он в теле оборота — до срока молчания, до обхода каналов и до
    проверки остановки. Дождись его оборот, и всё это время приложение не
    закрывалось бы, а кнопка «остановить» не помогала.

    Гасится он вместе с прочими чтениями переписки, в `mark_shutting_down`.
    """

    async def work() -> None:
        await catch_up_missed_dms(
            bot.ingestion.dm_helpers(),
            bot.ingestion.dm_hooks(),
            backfill_limit=bot.rs.dm_backfill_limit,
        )

    bot.ingestion.spawn_backfill(work, "dm catch-up")


async def _tick(bot, mode: BotMode) -> None:
    """Работа одного оборота: сроки молчания и, в полном режиме, обход каналов."""
    # Ghosting timer: дёргается каждый tick в активных
    # режимах (DM_ONLY и FULL). В OFF не запускается — бот
    # на паузе, не должен сам менять статусы. Сама проверка
    # дешёвая: только Applied/In Progress попадают в шорт-
    # лист, и при пустом списке ранний return.
    if mode is not BotMode.OFF:
        try:
            await bot.ingestion.check_ghosting_timeouts()
        except Exception:
            logger.exception("ghosting timer tick failed")
    # Channel polling and outbound applications are Full-only.
    # DM Only and Off both skip ingestion (DM Only still reacts
    # to incoming HR messages via the registered MessageHandler).
    if mode is BotMode.FULL:
        # Оборот может тихо не сделать ничего: место прогона мог
        # занять ручной прогон из окна.
        await slot.run_in_slot(bot, lambda: _ingest_round(bot), "poll cycle")


async def _ingest_round(bot) -> None:
    """Оборот приёма: сперва дочитать отложенное, потом идти за новым.

    Недоразобранная строка ждёт статьи, которой не хватило на приёме, и в
    окне её не видно вовсе — ни в списке, ни в отказах. Подбирай такие только
    при подъёме, и объявление ждало бы до следующего запуска приложения, а
    работает оно сутками.

    Сорвавшийся подбор обход не отменяет: свежие объявления человек ждёт
    больше, чем дочитанные.
    """
    try:
        await bot.ingestion.recover_orphan_vacancies()
    except Exception:
        logger.exception("orphan recovery failed")
    await bot.ingestion.poll_active_channels()


async def _sleep_until_wake(bot) -> None:
    """Дождаться срока следующего оборота или досрочного окрика из окна.

    Окрик гасится после пробуждения, а не перед ожиданием. Поданный, пока шёл
    оборот — а обход каналов идёт десятками минут, — он стирался бы негашеным
    ожиданием, и цикл засыпал бы на полный срок. Тумблером режима будят как
    раз затем, чтобы цикл увидел смену сразу: при уходе в OFF слил накопленную
    переписку в разбор, при возврате догнал пропущенное.
    """
    try:
        await asyncio.wait_for(
            bot.wake_event.wait(),
            timeout=bot.rs.poll_interval_sec,
        )
    except asyncio.TimeoutError:
        pass
    bot.wake_event.clear()


async def _disconnect(bot) -> None:
    """Погасить всё, что переживёт цикл: таски, соединение, клиенты модели."""
    logger.info("Bot run-loop exiting")
    # Shutdown-флаг ДО client.stop(): Pyrogram'овский DM-handler,
    # успевший отстрелить уже после teardown'а, увидит флаг и
    # no-op'нет вместо того, чтобы пытаться писать в закрытый
    # session_factory или дёргать httpx-клиенты, которые мы
    # сейчас будем aclose'ить.
    bot.ingestion.mark_shutting_down()
    # Висящие debounce-таски DM-классификации не должны жить дольше
    # бота — иначе при reload'е RuntimeSettings (новый Bot) старые
    # таски попытаются использовать закрытый httpx-клиент.
    try:
        await bot.ingestion.cancel_pending_dm_classifications()
    except Exception:
        logger.exception("cancel_pending_dm_classifications failed")
    # log_out_session() уже отключил клиент; повторный stop()
    # упадёт ConnectionError("Client is already terminated").
    # Глушим — логируем как debug.
    try:
        await bot.client.stop()
    except ConnectionError:
        logger.debug("Pyrogram client already terminated; skip stop()")
    except Exception:
        logger.exception("Pyrogram client.stop() failed")
    # Метка готовности снимается до закрытия клиентов модели, а не после: по
    # ней окно рисует лампочку связи, и сорвись закрытие — взведённая метка
    # осталась бы навсегда, показывая зелёный огонёк у бота, который уже
    # отключил Telegram.
    bot.loop = None
    if bot.lm_embed_client is not bot.lm_client:
        await bot.lm_embed_client.aclose()
    await bot.lm_client.aclose()


async def run(bot, *, once: bool = False) -> None:
    """Главный цикл бота: подъём, обороты по режиму, разборка за собой.

    Подъём стоит внутри разборки нарочно: два клиента модели собраны ещё до
    него, и сорвись `client.start()` — они пережили бы бота и держали бы
    гнёзда до конца работы приложения.

    Недоразобранные вакансии подбираются на каждом полном обороте, вместе с
    обходом каналов (`_ingest_round`), а не единожды при подъёме: строка ждёт
    там не только обрыва работы, но и статьи по ссылке, а та возвращается
    посреди рабочего дня.

    Режим OFF — полная остановка: ни догона переписки, ни разбора, ни обхода.
    Догон идёт на каждом переходе в рабочий режим, включая самый первый.
    """
    try:
        await _connect(bot)
        prev_mode = BotMode.OFF
        while True:
            mode = await current_mode(bot)
            await _on_mode_switch(bot, prev_mode, mode)
            await _tick(bot, mode)
            prev_mode = mode
            if once or bot.stop_event.is_set():
                # `_disconnect` логирует «Bot run-loop exiting» —
                # детали (once / stop_event) пишем DEBUG, чтобы не
                # дублировать INFO-строку.
                logger.debug(
                    "Run-loop terminating: once=%s stop_event=%s",
                    once,
                    bot.stop_event.is_set(),
                )
                return
            await _sleep_until_wake(bot)
            if bot.stop_event.is_set():
                logger.debug("Run-loop exiting after stop request")
                return
    finally:
        await _disconnect(bot)


async def persist_session_if_changed(bot) -> None:
    """After client.start(), export the (possibly fresh) session_string and
    write it back to runtime_settings if it differs from what we loaded.

    Covers two cases:
    * first interactive login (file-based session) — promotes to in-memory
      string on next run;
    * Telegram DC migrations / auth-key rotations — keeps the persisted
      copy in sync.
    """
    try:
        new_str = await bot.client.export_session_string()
    except Exception:
        logger.exception("export_session_string failed; not persisting")
        return
    tg = bot.rs.tg
    if tg is None:
        return
    if new_str == (tg.session_string or ""):
        return
    try:
        await bot.rs.set_tg(replace(tg, session_string=new_str))
        logger.info("persisted refreshed Telegram session_string")
    except Exception:
        logger.exception("persist session_string failed")
