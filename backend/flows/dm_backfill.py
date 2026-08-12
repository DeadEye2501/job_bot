"""Догон пропущенной переписки с HR."""

import logging
import asyncio
from itertools import batched
from dataclasses import dataclass
from typing import Any

from backend.flows.dm import persist_outgoing_dm, process_dm
from backend.domain.telegram_identity import telegram_peer
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
class _Walk:
    """Один проход по переписке: чей он и с чьей помощью идёт.

    **Это не свёртка группы значений, а носильщик сотрудников** — и разница
    названа нарочно. Соглашение плана сворачивает только настоящие группы, а
    здесь собраны Telegram, модель, база, планировщик и окно, то есть ровно
    тот мешок, который план отверг для `Bot.send`. Заведён он по другой
    причине: без него разнимание тела упирается в предел доводов у каждого
    куска. Публичная подпись догона при этом не тронута — её девять доводов
    остались доводами, и это записано в плане.

    Держит поля вместе один предмет — номер HR, чью переписку разбирают: все
    они живут ровно от первого сообщения прохода до последнего.
    """

    hr_id: int
    client: Any
    lm_client: Any
    lm_chat_model: str | None
    session_factory: Any
    schedule_classification: Any
    on_vacancies_changed: Any


async def _fetch_history(client, hr, limit: int) -> list | None:
    """Хвост переписки, свежими вперёд; `None` — прочитать не удалось.

    Пустой список этим не считается: он значит «переписки нет», и зовущий идёт
    дальше. Две беды чинятся здесь, обе одной попыткой. Неизвестный собеседник:
    номера нет в кэше, и `get_users` зовётся ради побочного действия — он
    кладёт собеседника туда, оттого второе чтение и проходит. Просьба
    подождать: сюда доходят только долгие (короткие Pyrogram пережидает сам),
    потому одной попытки и хватает, а второй отказ значит штраф до включения.
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
        wait = int(getattr(e, "value", 30))
        logger.info("backfill: FloodWait %ds на hr %d — жду и ретраим", wait, hr.id)
        await asyncio.sleep(wait + 1)
        try:
            return await read(target)
        except Exception:
            logger.exception("backfill: retry после FloodWait не помог hr %d", hr.id)
            return None


async def _store_outgoing(walk: _Walk, msg) -> bool:
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
            walk.session_factory, walk.client, msg, walk.hr_id
        )
    except Exception:
        logger.exception(
            "backfill outgoing insert failed",
            extra={"hr_id": walk.hr_id, "tg_message_id": msg.id},
        )
        return False
    return outcome == "stored"


async def _store_incoming(walk: _Walk, msg) -> bool:
    """Провести чужое сообщение той же дорогой, что и живое.

    Разбор и привязка к вакансии обязаны совпадать с живым путём, а повтор
    отсекает уникальность номера сообщения внутри `save_incoming_message`.

    С отложенным разбором о смене статуса оповещает он же, и отсюда сигнал
    не дублируется: после включения это полсотни сообщений на три десятка
    HR — полторы тысячи оповещений за миг. Без планировщика разбор идёт на
    месте, и сигнал нужен. Имя с приставкой: без неё запись о поломке не
    отличить от трёх других мест с тем же крючком.
    """
    try:
        await process_dm(
            msg, walk.lm_client, walk.lm_chat_model, walk.session_factory,
            client=walk.client,
            schedule_classification=walk.schedule_classification,
        )
    except Exception:
        logger.exception(
            "backfill incoming process failed",
            extra={"hr_id": walk.hr_id, "tg_message_id": msg.id},
        )
        return False
    if walk.schedule_classification is None:
        fire(walk.on_vacancies_changed, "backfill: on_vacancies_changed")
    return True


async def _walk_messages(messages: list, walk: _Walk) -> bool:
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
            had_new = await _store_outgoing(walk, msg) or had_new
        else:
            had_new = await _store_incoming(walk, msg) or had_new
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
    client, hr, lm_client, lm_chat_model, session_factory,
    *,
    backfill_limit: int,
    on_message_persisted=None, on_vacancies_changed=None,
    schedule_classification=None, newest_before: int = 0,
) -> None:
    """Pull the DM history of one HR and persist it.

    Used by ``catch_up_missed_dms`` (per-HR loop) and the auto-apply path
    (when ``find_or_create_hr`` just minted a new HR — without this hook the
    chat would show only the cover-letter we just sent).

    ``newest_before`` — наибольший номер письма, что был у нас **до** прохода;
    им сверка удалённого и отличает стёртое от пришедшего, пока мы читали.
    Снимает его зовущий: здесь это была бы работа с базой внутри задачи,
    которую гасят при остановке. Ноль значит «у нас ничего не было».
    """
    messages = await _fetch_history(client, hr, backfill_limit)
    if messages is None:
        return
    had_new = await _walk_messages(
        messages,
        _Walk(
            hr_id=hr.id,
            client=client,
            lm_client=lm_client,
            lm_chat_model=lm_chat_model,
            session_factory=session_factory,
            schedule_classification=schedule_classification,
            on_vacancies_changed=on_vacancies_changed,
        ),
    )
    tombstoned = await _reconcile_deletes(
        session_factory, hr.id, messages, newest_before
    )
    if had_new or tombstoned:
        fire(on_message_persisted, "on_message_persisted", hr.id)


def _report_failed(batch: list, results: list) -> None:
    """Пожаловаться на людей, чей проход сорвался.

    Сорвавшийся проход одного человека остальных не роняет: пачка собрана
    с `return_exceptions=True`, то есть беда приходит сюда значением, а не
    исключением, и разбирается после того, как пачка дошла целиком.
    """
    for (hr, _), result in zip(batch, results):
        if isinstance(result, Exception):
            logger.exception(
                "catch_up failed for hr %d", hr.id, exc_info=result,
            )


async def catch_up_missed_dms(
    client, lm_client, lm_chat_model, session_factory, backfill_limit: int,
    *,
    on_message_persisted=None, on_vacancies_changed=None,
    schedule_classification=None,
) -> None:
    """Pull recent DM history per known HR, both directions.

    Обе стороны — :func:`_store_outgoing`, удаления — :func:`_reconcile_deletes`.
    """
    # Отметки снимаются здесь и разом: до прохода, одной сессией и вне задач,
    # которые гасят при остановке. Ими сверка удалённого отличает стёртое от
    # пришедшего, пока шёл проход.
    async with session_factory() as session:
        chats = await list_hrs_for_backfill(session)
        newest = {hr.id: await newest_tg_message_id(session, hr.id) for hr, _ in chats}
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
                    client, hr, lm_client, lm_chat_model, session_factory,
                    backfill_limit=backfill_limit,
                    on_message_persisted=on_message_persisted,
                    on_vacancies_changed=on_vacancies_changed,
                    schedule_classification=schedule_classification,
                    newest_before=newest[hr.id],
                )
                for hr, _last_seen in batch
            ],
            return_exceptions=True,
        )
        _report_failed(batch, results)
        if index + 1 < len(batches):
            await asyncio.sleep(_DM_CATCHUP_BATCH_DELAY_SEC)


def spawn_hr_backfill(pipeline, hr) -> None:
    """Per-HR DM backfill kicked when a freshly-created HR is wired up
    from a parsed vacancy. Runs as a background task so the parse loop
    doesn't block on Telegram history fetch + media downloads. Pushes
    ``on_new_message`` per HR once the rows land — open chat in UI
    fills in without restart.

    Wajne: вызывать ПОСЛЕ ``try_auto_send`` для свежесозданного HR'а,
    иначе backfill может догнать через ``get_chat_history`` cover-
    letter сообщение раньше, чем ``Bot.send`` закоммитит свою row,
    и вставит её без ``vacancy_id`` (UNIQUE на (hr_id, tg_message_id,
    is_incoming) потом отстрелит Bot.send'овский insert).
    """
    async def _run() -> None:
        try:
            await backfill_hr_dm_history(
                pipeline._client, hr, pipeline._lm_client, pipeline._lm_chat_model,
                pipeline._session_factory,
                backfill_limit=pipeline._rs.dm_backfill_limit,
                on_message_persisted=pipeline.on_new_message,
                on_vacancies_changed=pipeline.on_vacancies_changed,
                schedule_classification=pipeline.schedule_dm_classification,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "spawn_hr_backfill failed for hr %d",
                hr.id, extra={"hr_id": hr.id},
            )
    task = asyncio.create_task(_run())
    pipeline._backfill_tasks.add(task)
    task.add_done_callback(pipeline._backfill_tasks.discard)
