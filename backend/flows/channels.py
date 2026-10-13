"""Обход телеграм-каналов за свежими постами."""

import logging
from typing import Literal

from backend.agent.stops import RUN_STOPPERS
from backend.telegram_lookup import read_channel_metadata
from backend.models import TelegramChannel
from backend.repository.channels import (
    is_channel_blacklisted,
    list_named_channels,
    set_channel_active,
)

from backend.flows import embeddings, ingest
from backend.notify import fire

logger = logging.getLogger(__name__)


# Отметка сохраняется пачками, а не после каждого сообщения: пятнадцать постов
# на полсотни каналов дали бы под тысячу записей на диск за цикл. Оборвись
# работа посреди пачки — до девяти уже разобранных постов примутся заново, а
# заведённое повторно срежет отсев по отпечатку.
BATCH_FLUSH_EVERY = 10

# Сколько подряд молчащих ответов поставщика отпечатков терпит один канал.
# Почему порог вообще есть — сказано у `_silence_broke_the_walk`.
_SILENCE_BEFORE_DROPPING_THE_CHANNEL = 3


async def poll_active_channels(pipeline) -> None:
    """Обойти каналы за свежими постами, обновив по дороге названия.

    Сводка названий идёт по всем каналам с ником, включая выключенные: они
    видны в окне, и человек ждёт у них свежих данных. Отбор по включённости
    решает только чтение сообщений — оно и стоит минуты против её секунд.

    Сорвавшаяся сводка обход не отменяет: она второстепенна — названия и
    картинки, — а следующий цикл идёт через полтора часа, и объявления этого
    человек не увидел бы вовсе.

    Выключенный общий выключатель каналов гасит обход целиком, вместе со
    сводкой: тумблеры строк он не трогает, и включённые каналы просто ждут.
    """
    if not pipeline.rs.channels_enabled:
        logger.info("Poll cycle skipped: channels are switched off as a whole")
        return
    await pipeline.reload_resources()
    async with pipeline.session_factory() as session:
        all_named = await list_named_channels(session)

    try:
        await refresh_channel_metadata(pipeline, all_named)
    except Exception:
        logger.exception("Сводка названий сорвалась, иду читать сообщения")

    active_named = [c for c in all_named if c.is_active]
    total = len(active_named)
    logger.info(
        "Poll cycle start: %d named channels (%d active)",
        len(all_named),
        total,
    )
    for idx, ch in enumerate(active_named):
        pipeline.emit_progress("channel", f"@{ch.username}", idx, total)
        await _walk_channel(pipeline, ch)
    pipeline.emit_progress("channel", "", total, total)
    # 0/0 on the message track signals the UI to clear that bar between
    # cycles; otherwise it would freeze on the last channel's count.
    pipeline.emit_progress("message", "", 0, 0)
    logger.info("Poll cycle done")


async def _walk_channel(pipeline, ch) -> None:
    """Прочитать один канал обхода; его беда обход не обрывает.

    Канал, чей ник никем не занят, удалён или переименован: вакансий оттуда
    не будет, а чтение каждый круг тратит розыск по нику, на частый розыск
    Telegram отвечает запретом на часы — на весь аккаунт. Такой канал
    выключается; вернуть его — тумблером, если ник снова заведут.
    """
    from pyrogram.errors import UsernameNotOccupied

    try:
        await poll_channel(pipeline, ch.id, ch.username, ch.last_processed_msg_id)
    except RUN_STOPPERS:
        raise
    except UsernameNotOccupied:
        logger.warning("[@%s] канала больше нет — ник никем не занят; выключаю", ch.username)
        await _switch_off(pipeline, ch)
    except Exception:
        logger.exception("[@%s] poll failed", ch.username)


async def _switch_off(pipeline, ch) -> None:
    """Выключить канал и сказать окну; беда записи обход не обрывает."""
    try:
        async with pipeline.session_factory() as session:
            await set_channel_active(session, ch.id, False)
            await session.commit()
    except Exception:
        logger.exception("[@%s] выключить не вышло", ch.username)
        return
    fire(pipeline.on_channels_changed, "on_channels_changed")


PollOutcome = Literal["ok", "missing", "blacklisted", "error"]
"""Чем кончился прогон одного канала на конвейере.

Место прогона и его исходы («занято», «остановили») сюда не входят: этим
распоряжается слой выше, и там имя складывается с `slot.CycleOutcome`.
"""


async def poll_one_channel(pipeline, channel_id: int) -> PollOutcome:
    """Run metadata refresh + message polling for a single channel.

    UI's «Прогнать сейчас» — taps this without touching the global poll loop,
    so it doesn't have to wait through 17 other channels in a 90-min cycle.

    Исходы разведены нарочно: окно говорит о них разное, и одинаковый ответ
    посылал бы человека искать запись, которая на месте, пока настоящая
    причина — закрытый канал, просьба подождать, молчание модели — оставалась
    бы только в журнале.

    Выключенный канал прогнать руками можно — тем ручной прогон и отличается
    от обхода. Канал в чёрном списке — нельзя: его заносили туда затем, чтобы
    он больше не приносил вакансий, а отсев по тексту от этого не спасает —
    он сверяет текст поста, а написание канала это `@ник`, которого в теле
    поста обычно нет.

    Ловушка обнимает один обход постов, и польза от неё одна — ник канала в
    записи журнала. Всё, что до неё, ловит место прогона, и его «сорвалось»
    приводит окно к тому же слову, что и здешний `"error"`.
    """
    await pipeline.reload_resources()
    async with pipeline.session_factory() as session:
        named = await list_named_channels(session, ids=[channel_id])
        if not named:
            return "missing"
        if await is_channel_blacklisted(session, channel_id):
            logger.info("[@%s] manual poll refused: channel is blacklisted",
                        named[0].username)
            return "blacklisted"
        username = named[0].username
        last_id = named[0].last_processed_msg_id
    await refresh_channel_metadata_for_ids(pipeline, [channel_id])
    try:
        walked_whole = await poll_channel(pipeline, channel_id, username, last_id)
    except RUN_STOPPERS:
        raise
    except Exception:
        logger.exception("[@%s] manual poll failed", username)
        return "error"
    return "ok" if walked_whole else "error"


async def refresh_channel_metadata_for_ids(pipeline, channel_ids: list[int]) -> None:
    """Public entry point for one-off metadata refresh — например,
    после ручного «Добавить канал» из UI: сразу же тянем title/avatar,
    чтобы пользователь не ждал следующего поллинга.
    Делегирует во внутренний sweep, который и кидает on_channels_changed.
    """
    if not channel_ids:
        return
    logger.debug("refresh metadata for %d channel(s)", len(channel_ids))
    async with pipeline.session_factory() as session:
        rows = await list_named_channels(session, ids=channel_ids)
    await refresh_channel_metadata(pipeline, rows)


async def _store_metadata(
    pipeline, title_updates: dict[int, str], avatar_updates: dict[int, bytes]
) -> None:
    """Записать собранное за обход — всё одной транзакцией."""
    async with pipeline.session_factory() as session:
        for channel_id in set(title_updates) | set(avatar_updates):
            db_ch = await session.get(TelegramChannel, channel_id)
            if db_ch is None:
                continue
            new_title = title_updates.get(channel_id)
            if new_title is not None and db_ch.title != new_title:
                db_ch.title = new_title
            blob = avatar_updates.get(channel_id)
            # «Пусто ли место» спрашивается второй раз нарочно: строка
            # перечитана в новой сессии, и картинка могла появиться у неё за
            # время обхода — обход идёт по каналам последовательно.
            if blob is not None and db_ch.avatar is None:
                db_ch.avatar = blob
        await session.commit()


async def _collect_metadata(pipeline, channels) -> tuple[dict, dict]:
    """Спросить у Telegram названия и картинки; отдать то, что стоит записать.

    Обращение на канал одно и идёт по очереди: соединение Pyrogram одно на
    всех, а частые обращения упираются в предел. Ответ несёт и название, и
    картинку сразу. Что берётся у ответа и по какому правилу — в
    `telegram_lookup.read_channel_metadata`; здесь остаётся своё: название
    попадает в сбор только изменившееся.

    Канал, до которого не достучались, пропускается с записью в журнал: из-за
    одного закрытого остальные обновиться должны. Канал, которого нет вовсе,
    — одной строкой: обход его уже выключил, а сводка идёт и по выключенным.
    """
    from pyrogram.errors import UsernameNotOccupied

    title_updates: dict[int, str] = {}
    avatar_updates: dict[int, bytes] = {}
    for ch in channels:
        try:
            chat = await pipeline.client.get_chat(ch.username)
        except UsernameNotOccupied:
            logger.info("[@%s] канала нет — название не обновить", ch.username)
            continue
        except Exception:
            logger.exception("[@%s] get_chat failed", ch.username)
            continue
        new_title, blob = await read_channel_metadata(
            pipeline.client, chat, current_avatar=ch.avatar
        )
        if new_title and new_title != ch.title:
            title_updates[ch.id] = new_title
        if blob:
            avatar_updates[ch.id] = blob
    return title_updates, avatar_updates


async def refresh_channel_metadata(pipeline, channels) -> None:
    """Обновить название и аватар у каждого канала с ником, до чтения постов.

    У каждого, а не только у включённых: выключенные всё равно стоят в списке
    окна, и человек ждёт у них свежих данных. Отбор по включённости решает
    только чтение постов ниже.

    Спрашивает сосед (`_collect_metadata`), здесь остаётся запись: всё
    собранное ложится одной сделкой, и окно узнаёт о свежих названиях только
    после неё — не записанному радоваться нечему.
    """
    title_updates, avatar_updates = await _collect_metadata(pipeline, channels)
    if not title_updates and not avatar_updates:
        return
    try:
        await _store_metadata(pipeline, title_updates, avatar_updates)
    except Exception:
        # Занятая база — обычное дело: рядом идёт запись входящего письма.
        # Названия подождут следующего обхода, а вот бросок отсюда уносит и
        # ручной прогон канала, и весь цикл сразу за сводкой.
        logger.exception("Не записал названия и картинки каналов")
        return
    logger.info(
        "refresh_channel_metadata: %d title(s), %d avatar(s) updated",
        len(title_updates), len(avatar_updates),
    )
    fire(pipeline.on_channels_changed, "on_channels_changed")


async def _unseen_posts(pipeline, channel_username: str, last_id: int | None):
    """Посты канала, которых мы ещё не видели, — старые первыми, не больше
    предела за обход.

    С отметкой канал читается свежими вперёд до первого уже виденного, и
    берутся старейшие непрочитанные: отметка сдвигается только по прочитанному,
    а остальное возьмут следующие обходы. Возьми свежие — и после простоя,
    когда новых больше предела, середина между отметкой и ними пропала бы.

    Без отметки — первый обход — берётся предел самых свежих: это глубина
    первого захода, читать «до виденного» нечего.
    """
    limit = pipeline.rs.backfill_limit
    client = pipeline.client
    if last_id is None:
        newest = [msg async for msg in client.get_chat_history(channel_username, limit=limit)]
        return list(reversed(newest))
    unseen = []
    async for msg in client.get_chat_history(channel_username):
        if msg.id <= last_id:
            break
        unseen.append(msg)
    return list(reversed(unseen))[:limit]


async def _take_post(pipeline, channel_id: int, channel_username: str, msg) -> bool:
    """Принять один пост; `False` — поставщик отпечатков молчит.

    Сорвавшийся приём здесь беды не делает и отметку не держит: сломанное
    сообщение иначе перечитывалось бы вечно, а что успело завестись — срежет
    отсев повторов. Молчание поставщика решается зовущим: пост не считали
    вовсе, и двигать отметку значит потерять его.
    """
    try:
        await ingest.ingest_post(pipeline, channel_id, channel_username, msg)
    except embeddings.ProviderIsSilent:
        return False
    except RUN_STOPPERS:
        raise
    except Exception:
        logger.exception(
            "[@%s] %d ingest failed, advancing cursor", channel_username, msg.id,
        )
    return True


def _silence_broke_the_walk(channel_username: str, msg_id: int, silence: int) -> bool:
    """Записать осечку поставщика; `True` — обход пора бросать.

    Молчит поставщик сразу для всех, и перебор оставшихся постов — десятки
    напрасных обращений и минуты на канал, за которыми всё равно ничего не
    заводится. Порог считает осечки подряд: одиночная бывает и от медленной
    выдачи сразу после загрузки модели.
    """
    logger.warning(
        "[@%s] %d поставщик отпечатков молчит (%d подряд)",
        channel_username, msg_id, silence,
    )
    if silence < _SILENCE_BEFORE_DROPPING_THE_CHANNEL:
        return False
    logger.error(
        "[@%s] бросаю обход: поставщик отпечатков молчит %d подряд",
        channel_username, silence,
    )
    return True


async def poll_channel(
    pipeline,
    channel_id: int,
    channel_username: str,
    last_id: int | None,
) -> bool:
    """Вычитать новые посты канала; `False` — обход брошен, а не пройден.

    Отметку держит первая же осечка, а не третья: см. `_take_post`. Посты
    после неё заводятся и на следующем обходе срезаются отсевом повторов.
    """
    ordered = await _unseen_posts(pipeline, channel_username, last_id)
    total = len(ordered)
    cursor: int | None = None
    held = False
    silence = 0
    walked_whole = False
    try:
        for i, msg in enumerate(ordered):
            pipeline.emit_progress("message", f"@{channel_username}", i, total)
            if not await _take_post(pipeline, channel_id, channel_username, msg):
                held = True
                silence += 1
                if _silence_broke_the_walk(channel_username, msg.id, silence):
                    break
                continue
            silence = 0
            if held:
                continue
            cursor = msg.id
            if (i + 1) % BATCH_FLUSH_EVERY == 0:
                await advance_cursor(pipeline, channel_id, cursor)
        else:
            walked_whole = True
    finally:
        # Полосу дозаполняем и на брошенном обходе: пока цикл идёт к
        # следующему каналу, она иначе стоит на счёте брошенного. С экрана её
        # снимает не это, а конец прогона — по нему окно убирает обе полосы.
        pipeline.emit_progress("message", f"@{channel_username}", total, total)
        if cursor is not None:
            await advance_cursor(pipeline, channel_id, cursor)
    return walked_whole


async def advance_cursor(pipeline, channel_id: int, msg_id: int) -> None:
    async with pipeline.session_factory() as session:
        ch = await session.get(TelegramChannel, channel_id)
        if ch is None:
            return
        ch.last_processed_msg_id = msg_id
        await session.commit()
    logger.debug(
        "advance_cursor: channel=%d -> msg_id=%d", channel_id, msg_id,
    )
