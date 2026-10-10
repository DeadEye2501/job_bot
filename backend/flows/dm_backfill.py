"""Догон пропущенной переписки с HR."""

import logging
import asyncio
from itertools import batched
from dataclasses import dataclass
from typing import Any

from backend.flows.batches import report_failures
from backend.flows.dm import DmHelpers, persist_outgoing_dm, process_dm
from backend.domain.telegram_identity import hrs_in_dialog_order, telegram_peer
from backend.models import Message
from backend.repository.hr_list import list_hrs_for_backfill
from backend.repository.messages import newest_tg_message_id, tombstone_messages
from backend.notify import fire

logger = logging.getLogger(__name__)


# DM catch-up batching: ``BATCH_SIZE`` HR'ов параллельно через
# ``asyncio.gather``, потом ``BATCH_DELAY_SEC`` пауза перед следующим
# батчем — чтобы TG-rate-limit window успевал сбрасываться. Параметры
# подобраны под flood_sleep_threshold=60 в adapters/telegram.py: даже
# если внутри батча словим короткий FloodWait, Pyrogram съест его сам.
_DM_CATCHUP_BATCH_SIZE = 20


_DM_CATCHUP_BATCH_DELAY_SEC = 1.0


@dataclass(frozen=True, slots=True)
class DmHooks:
    """Чем догон будит окно: пришло письмо и сменился статус вакансии.

    Ходят вдвоём везде, где ходят вообще: обоих зовущий берёт у одного и того
    же конвейера и передаёт насквозь до самого прохода по переписке.
    """

    on_message_persisted: Any = None
    on_vacancies_changed: Any = None


async def _fetch_history(client, hr, limit: int) -> list | None:
    """Хвост переписки, свежими вперёд; `None` — прочитать не удалось.

    Пустой список этим не считается: он значит «переписки нет», и зовущий идёт
    дальше. Неизвестный собеседник чинится здесь же, одной попыткой: номера
    нет в кэше, и `get_users` зовётся ради побочного действия — он кладёт
    собеседника туда, оттого второе чтение и проходит.

    Просьбу «слишком часто» не пережидают вовсе. Короткие Pyrogram переживает
    сам (`sleep_threshold`), значит сюда доходят только долгие — минуты и
    часы. Столько держать переписку одного собеседника незачем: догон идёт по
    всем разом, и пережидающий занял бы своё место в пачке до конца ожидания.
    Пропущенное не теряется: догон повторится на следующем подъёме соединения.
    """
    from pyrogram.errors import FloodWait, PeerIdInvalid

    async def read(peer) -> list:
        return [msg async for msg in client.get_chat_history(peer, limit=limit)]

    target = telegram_peer(hr)
    if target is None:
        return None
    try:
        return await read(target)
    except PeerIdInvalid:
        logger.warning("backfill: PeerIdInvalid у hr %d — пробую по нику", hr.id)
        if not hr.telegram_username:
            return None
        try:
            await client.get_users(hr.telegram_username)
            return await read(hr.telegram_username)
        except Exception:
            logger.exception("backfill: resolve fallback failed для hr %d", hr.id)
            return None
    except FloodWait as e:
        logger.warning(
            "backfill: FloodWait %ss на hr %d — пропускаю до следующего раза",
            getattr(e, "value", "?"), hr.id,
        )
        return None


async def _store_outgoing(hr_id: int, dm: DmHelpers, msg) -> bool:
    """Записать своё сообщение из хвоста; сказать, легло ли новое.

    Разбора моделью оно не требует — пишется как есть, тем же объявлением,
    что и эхо из Telegram.

    Свои сообщения тянутся из хвоста затем, что человек мог писать HR с
    телефона или другого клиента, пока бот стоял: без них в переписке
    видно только отправленное нами и присланное HR, то есть половина
    разговора. Повторы отсекает `persist_outgoing_dm` — он же решает,
    считать ли сообщение новым, и уже лежащую строку новой не считает.
    """
    try:
        outcome = await persist_outgoing_dm(
            dm.session_factory, dm.client, msg, hr_id
        )
    except Exception:
        logger.exception(
            "backfill outgoing insert failed",
            extra={"hr_id": hr_id, "tg_message_id": msg.id},
        )
        return False
    return outcome == "stored"


async def _store_incoming(hr_id: int, dm: DmHelpers, hooks: DmHooks, msg) -> bool:
    """Провести чужое сообщение той же дорогой, что и живое.

    Разбор и привязка к вакансии обязаны совпадать с живым путём, а повтор
    отсекает уникальность номера сообщения внутри `save_incoming_message`.

    С отложенным разбором о смене статуса оповещает он же, и отсюда сигнал
    не дублируется: после включения это полсотни сообщений на три десятка
    HR — полторы тысячи оповещений за миг. Без планировщика разбор идёт на
    месте, и сигнал нужен. Имя с приставкой: без неё запись о поломке не
    отличить от трёх других мест с тем же крючком.

    «Легло» берётся из ответа `process_dm`, а не из отсутствия поломки: догон
    видит уже записанное почти всегда, и повтор, засчитанный за новость, будил
    бы окно по каждой переписке при каждом включении.
    """
    try:
        landed = await process_dm(msg, dm) is not None
    except Exception:
        logger.exception(
            "backfill incoming process failed",
            extra={"hr_id": hr_id, "tg_message_id": msg.id},
        )
        return False
    if landed and dm.schedule_classification is None:
        fire(hooks.on_vacancies_changed, "backfill: on_vacancies_changed")
    return landed


async def _walk_messages(
    messages: list, hr_id: int, dm: DmHelpers, hooks: DmHooks
) -> bool:
    """Записать вытянутую переписку; сказать, появилось ли новое.

    Старое первым: Telegram отдаёт свежее вперёд, а в переписке окна порядок
    обратный. Беда одного сообщения весь догон не уносит — дальше идут и
    остальная переписка, и сверка удалённого, и оповещение окна; догон
    вдобавок гоняют по два десятка переписок разом, и запертая на запись
    база тут обычное дело.
    """
    had_new = False
    for msg in reversed(messages):
        if msg.outgoing:
            had_new = await _store_outgoing(hr_id, dm, msg) or had_new
        else:
            had_new = await _store_incoming(hr_id, dm, hooks, msg) or had_new
    return had_new


async def _reconcile_deletes(
    session_factory, hr_id: int, messages: list, newest_before: int
) -> bool:
    """Похоронить строки, пропавшие из ответа Telegram; сказать, были ли такие.

    Telegram не переигрывает пропущенные оповещения об удалении после
    переподключения. Окно сверки — номера, накрытые вытянутым хвостом: всё,
    что в него попадает, но в ответе не пришло, удалено, пока нас не было.

    Границы у окна две, и верхняя не менее важна нижней. Ниже окна лежит
    переписка, до которой хвост не достал. Выше — письмо, пришедшее живым
    обработчиком, пока догон читал: в ответе его нет по той же причине, по
    какой нет удалённого, ответ собран раньше.

    Различает их только ``newest_before`` — отметка, снятая **до** запроса
    истории. Что было у нас тогда, то Telegram и обязан был вернуть, а
    появившееся позже вернуть не мог. Возьми верхней границей `max` по
    ответу — и удалённое последнее письмо не похоронится уже никогда, потому
    что других путей у этой строки нет.
    """
    if not messages:
        return False
    seen_ids = {m.id for m in messages}
    async with session_factory() as session:
        buried = bool(
            await tombstone_messages(
                session,
                Message.hr_id == hr_id,
                Message.tg_message_id.is_not(None),
                Message.tg_message_id >= min(seen_ids),
                Message.tg_message_id <= max(max(seen_ids), newest_before),
                Message.tg_message_id.notin_(seen_ids),
            )
        )
        if buried:
            await session.commit()
    return buried


async def backfill_hr_dm_history(
    hr, dm: DmHelpers, hooks: DmHooks,
    *,
    backfill_limit: int,
    newest_before: int = 0,
) -> None:
    """Pull the DM history of one HR and persist it.

    Used by ``catch_up_missed_dms`` (per-HR loop) and the auto-apply path
    (when ``find_or_create_hr`` just minted a new HR — without this hook the
    chat would show only the cover-letter we just sent).

    ``newest_before`` — наибольший номер письма, что был у нас **до** прохода;
    им сверка удалённого и отличает стёртое от пришедшего, пока мы читали.
    Снимает его зовущий: догон идёт по всем собеседникам разом, и снятая там
    отметка стоит одной сессии на всех вместо сессии на каждого, а снята она
    до первой пачки — то есть до того, как хоть кто-то начал читать. Ноль
    значит «у нас ничего не было».
    """
    messages = await _fetch_history(dm.client, hr, backfill_limit)
    if messages is None:
        return
    had_new = await _walk_messages(messages, hr.id, dm, hooks)
    tombstoned = await _reconcile_deletes(
        dm.session_factory, hr.id, messages, newest_before
    )
    if had_new or tombstoned:
        fire(hooks.on_message_persisted, "on_message_persisted", hr.id)


async def catch_up_missed_dms(
    dm: DmHelpers, hooks: DmHooks, *, backfill_limit: int, dialogs=()
) -> None:
    """Догнать переписку по всем известным собеседникам, свежими вперёд.

    Обе стороны — :func:`_store_outgoing`, удаления — :func:`_reconcile_deletes`.

    `dialogs` — список переписок, прочитанный при подъёме соединения. Им
    правится очередь: впереди идут те, с кем разговор есть, свежими вперёд —
    человек, открывший приложение, ждёт свежее письмо, а не полного обхода
    всех. Остальные досматриваются следом; пустой список просто оставляет
    прежний порядок.
    """
    # Отметки снимаются здесь и разом: до прохода и одной сессией. Ими сверка
    # удалённого отличает стёртое от пришедшего, пока шёл проход.
    async with dm.session_factory() as session:
        chats = hrs_in_dialog_order(await list_hrs_for_backfill(session), dialogs)
        newest = {hr.id: await newest_tg_message_id(session, hr.id) for hr in chats}
    logger.info(
        "DM catch-up: %d HR(s), batch=%d delay=%ss",
        len(chats), _DM_CATCHUP_BATCH_SIZE, _DM_CATCHUP_BATCH_DELAY_SEC,
    )
    # Пачками — иначе 300-500 HR'ов дают столько же последовательных
    # обращений; внутри пачки параллельно, пауза после — ради ограничителя.
    batches = list(batched(chats, _DM_CATCHUP_BATCH_SIZE))
    for index, batch in enumerate(batches):
        results = await asyncio.gather(
            *[
                backfill_hr_dm_history(
                    hr, dm, hooks,
                    backfill_limit=backfill_limit,
                    newest_before=newest[hr.id],
                )
                for hr in batch
            ],
            return_exceptions=True,
        )
        report_failures([hr.id for hr in batch], results, "catch_up", logger)
        if index + 1 < len(batches):
            await asyncio.sleep(_DM_CATCHUP_BATCH_DELAY_SEC)


def spawn_hr_backfill(pipeline, hr) -> None:
    """Per-HR DM backfill kicked when a freshly-created HR is wired up
    from a parsed vacancy. Runs as a background task so the parse loop
    doesn't block on Telegram history fetch + media downloads. Pushes
    ``on_new_message`` per HR once the rows land — open chat in UI
    fills in without restart.

    Зовёт его передача отобранного (`flows/handover`) — после отклика:
    пойди догон первым, он вытащил бы наше письмо через ``get_chat_history``
    раньше, чем откликатель запишет свою строку, и положил бы её без
    ``vacancy_id``.
    """
    async def work() -> None:
        await backfill_hr_dm_history(
            hr,
            pipeline.dm_helpers(),
            pipeline.dm_hooks(),
            backfill_limit=pipeline.rs.dm_backfill_limit,
        )

    pipeline.spawn_backfill(
        work, f"spawn_hr_backfill for hr {hr.id}", extra={"hr_id": hr.id}
    )
