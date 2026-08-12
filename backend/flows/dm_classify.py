"""Разбор переписки с HR языковой моделью."""

import logging
import asyncio

from backend.flows.auto_gate import status_open_for_auto
from backend.llm.hr_reply import classify_hr_reply
from backend.models import VacancyStatus
from backend.payloads import PendingReply
from backend.repository.vacancies_life import apply_classification
from backend.notify import fire

logger = logging.getLogger(__name__)


def update_dm_buffer_text(pipeline, hr_id: int, tg_msg_id: int, new_text: str) -> None:
    """HR отредактировал сообщение пока оно сидит в debounce-буфере —
    обновим текст, чтобы LLM-классификатор видел свежее содержимое.

    Ищется письмо по номеру Telegram: оповещение о правке приходит оттуда и
    другого номера не знает. Номер строки базы лежит в копилке рядом и
    служит другому — записи вердикта.
    """
    buf = pipeline._dm_classify_buffer.get(hr_id)
    if not buf:
        return
    for item in buf:
        if item["tg_msg_id"] == tg_msg_id:
            item["text"] = new_text or ""
            break


def remove_dm_buffer_msg(pipeline, hr_id: int, tg_msg_id: int) -> None:
    """HR удалил сообщение пока оно сидит в debounce-буфере — выкинем
    его из burst'а, чтобы не учитывать в классификации.

    По номеру Telegram, по той же причине, что и правка.
    """
    buf = pipeline._dm_classify_buffer.get(hr_id)
    if not buf:
        return
    pipeline._dm_classify_buffer[hr_id] = [
        item for item in buf if item["tg_msg_id"] != tg_msg_id
    ]
    if not pipeline._dm_classify_buffer[hr_id]:
        pipeline._dm_classify_buffer.pop(hr_id, None)


def schedule_dm_classification(pipeline, hr_id: int, reply: PendingReply) -> None:
    """Append text to per-HR burst buffer и (пере-)взводит таймер на
    DM_CLASSIFY_DEBOUNCE_SEC. Когда таймер дотикает (новых сообщений
    от HR не приходило), таск ``_run_debounced_classify`` соберёт
    пакет и сделает один LLM-вызов.
    """
    if pipeline._shutting_down:
        return
    if not reply.text:
        # Медиа-only без подписи нечем классифицировать. Пропускаем
        # тихо — само сообщение уже в БД.
        return
    buf = pipeline._dm_classify_buffer.setdefault(hr_id, [])
    buf.append({
        "vacancy_id": reply.vacancy_id,
        "msg_id": reply.message_id,
        "tg_msg_id": reply.tg_message_id,
        "text": reply.text,
    })
    # Cap: спам / зацикленный HR не должен раздувать память.
    # Drop oldest, оставляя последние DM_CLASSIFY_BUFFER_CAP штук —
    # «свежий сигнал» важнее «полной истории», тем более что
    # classify_hr_reply всё равно режет последние 4000 chars.
    if len(buf) > pipeline.DM_CLASSIFY_BUFFER_CAP:
        dropped = len(buf) - pipeline.DM_CLASSIFY_BUFFER_CAP
        del buf[: dropped]
        logger.warning(
            "schedule_dm_classification: hr %d burst > %d msgs, "
            "dropping oldest %d",
            hr_id, pipeline.DM_CLASSIFY_BUFFER_CAP, dropped,
        )
    prev = pipeline._dm_classify_tasks.get(hr_id)
    if prev is not None and not prev.done():
        prev.cancel()
    pipeline._dm_classify_tasks[hr_id] = asyncio.create_task(
        _run_debounced_classify(pipeline, hr_id)
    )


async def classify_and_apply(
    session_factory,
    lm_client,
    lm_chat_model,
    text: str,
    target: tuple[int, int, VacancyStatus],
) -> bool:
    """Спросить модель о письме и применить вердикт; отдать, применён ли он.

    Дорог две — отложенный разбор пачки и разбор одного письма на месте, — и
    правило у них одно: пустой вердикт ничего не двигает, а применение идёт
    своей транзакцией, потому что чужой рядом нет.

    `target` — «вакансия, письмо, её нынешний статус»: три довода, которые
    все три описывают одно, к чему прикладывают вердикт, и порознь ни один
    из них здесь не нужен.
    """
    vacancy_id, msg_id, status = target
    verdict = await classify_hr_reply(text, status, lm_client, lm_chat_model)
    if verdict is None:
        logger.info("vacancy %s: classifier gave nothing", vacancy_id)
        return False
    logger.info(
        "vacancy %s: classifier verdict=%s -> applying",
        vacancy_id, verdict.status.value,
    )
    async with session_factory() as session:
        try:
            await apply_classification(
                session, vacancy_id, msg_id, verdict
            )
            await session.commit()
        except Exception:
            logger.exception(
                "classification apply failed",
                extra={"vacancy_id": vacancy_id, "message_id": msg_id},
            )
            return False
    return True


async def _run_debounced_classify(pipeline, hr_id: int) -> None:
    try:
        await asyncio.sleep(pipeline.DM_CLASSIFY_DEBOUNCE_SEC)
    except asyncio.CancelledError:
        return  # перепланировано более свежим сообщением — выходим тихо
    # Identity-check ДО pop'а буфера: если за время sleep'а прилетело
    # новое schedule_dm_classification, оно cancel'нуло нас и положило
    # в _dm_classify_tasks свой task. Если мы pop'нем буфер, новый
    # task получит пусто и тоже выйдет тихо — burst пропадёт. Сначала
    # удостоверимся, что мы всё ещё «owner» этого hr_id.
    current = asyncio.current_task()
    if pipeline._dm_classify_tasks.get(hr_id) is not current:
        return  # superseded — буфер не трогаем, пусть новый task его драйнит
    pipeline._dm_classify_tasks.pop(hr_id, None)
    # Защита от race shutdown'а: между sleep'ом и сюда могли вызвать
    # mark_shutting_down + cancel_pending. Если флаг — выходим без
    # LLM-вызова и БД-записи (sessions/clients уже закрываются).
    if pipeline._shutting_down:
        return
    pipeline._dm_classify_running.add(current)
    try:
        await classify_and_apply_for_hr(pipeline, hr_id)
    finally:
        pipeline._dm_classify_running.discard(current)


async def _blacklisted_now(pipeline, hr_id: int) -> str | None:
    """Написание, из-за которого HR числится в чёрном списке прямо сейчас.

    Спрашивается заново: человек мог попасть в список между приходом
    письма и сроком разбора. Входящие от него в копилку уже не ложатся, но
    накопленный до этого пакет разбирать тоже незачем.
    """
    from backend.models import HR
    from backend.repository.hr_card import hr_blacklist_value

    async with pipeline._session_factory() as session:
        hr_row = await session.get(HR, hr_id)
        return await hr_blacklist_value(session, hr_row) if hr_row else None


async def _ask_and_apply(pipeline, hr_id: int, burst: list, target) -> None:
    """Спросить модель по склеенному пакету и применить вердикт.

    Одновременных обращений столько, сколько разрешает семафор конвейера:
    без него переход в рабочий режим будит разборы по всем людям разом.

    Размер пачки идёт в запись о поломке: сама пачка к этому мигу уже вынута
    из копилки и потеряна, и число — единственное, что о ней скажет.
    """
    try:
        async with pipeline._dm_classify_semaphore:
            applied = await classify_and_apply(
                pipeline._session_factory,
                pipeline._lm_client,
                pipeline._lm_chat_model,
                _burst_text(burst),
                target,
            )
    except Exception:
        logger.exception(
            "debounced classify failed for hr %d (%d msgs)", hr_id, len(burst)
        )
        return
    if applied:
        fire(pipeline.on_vacancies_changed, "on_vacancies_changed")


def _burst_text(buf: list[dict]) -> str:
    """Склеить пакет в один текст двойным переносом.

    Перенос двойной затем, чтобы модель видела границы отдельных сообщений
    и выбирала самый продвинутый признак (предложение > приглашение >
    тестовое > отказ > ответили) по всему пакету, а не по последней строке.
    """
    return "\n\n".join(item["text"] for item in buf)


async def classify_and_apply_for_hr(pipeline, hr_id: int) -> None:
    """Drain burst-буфера для hr_id: один LLM-вызов на накопленный
    пакет → apply_classification. Используется и из debounce-тика,
    и из drain-on-OFF в `cancel_pending_dm_classifications`.
    """
    bl_value = await _blacklisted_now(pipeline, hr_id)
    if bl_value:
        logger.info(
            "debounced classify: hr %d in blacklist (%s) — drop burst",
            hr_id, bl_value,
        )
        pipeline._dm_classify_buffer.pop(hr_id, None)
        return
    buf = pipeline._dm_classify_buffer.pop(hr_id, [])
    if not buf:
        return
    last = buf[-1]
    vacancy_id = last["vacancy_id"]
    msg_id = last["msg_id"]
    # Срезаем здесь, а не полагаемся на `should_apply_status` внутри
    # `apply_classification`: тот отобьёт вердикт уже после обращения к
    # модели, то есть заплатив за него.
    is_open, v_status = await status_open_for_auto(
        pipeline._session_factory, vacancy_id
    )
    if not is_open:
        logger.info(
            "vacancy %s: status=%s closed for auto, "
            "drop debounced burst (hr %d, %d msgs)",
            vacancy_id, v_status.value if v_status else "gone", hr_id, len(buf),
        )
        return
    logger.info(
        "debounced classify: hr %d, %d msgs in burst -> vacancy %s",
        hr_id, len(buf), vacancy_id,
    )
    await _ask_and_apply(pipeline, hr_id, buf, (vacancy_id, msg_id, v_status))


async def _wait_out(pipeline, tasks: list, *, drain: bool) -> None:
    """Переждать разборы, а на выключении погасить не уложившихся.

    Выключение закрывает соединения, и опоздавший разбор пришёл бы в
    закрытую сессию — потеря его пакета меньшее зло. Переход в OFF ничего
    не закрывает, и там ему дают доработать.
    """
    _, pending = await asyncio.wait(
        tasks, timeout=pipeline.DM_CLASSIFY_STOP_TIMEOUT_SEC
    )
    if not pending:
        return
    logger.warning(
        "cancel_pending_dm_classifications: %d task(s) did not finish in time",
        len(pending),
    )
    if drain:
        return
    for t in pending:
        t.cancel()


async def _cancel_and_wait(pipeline, *, drain: bool) -> None:
    """Отменить спящие разборы и дождаться уже начавшихся.

    Отмена достаётся только спящим на таймере: они и числятся в
    `_dm_classify_tasks`. Начавшийся разбор вычёркивает себя оттуда сам и
    переходит в `_dm_classify_running` — его дожидаются, но не отменяют:
    пакет он из буфера уже вынул, и отмена потеряла бы его насовсем.
    """
    tasks = [t for t in pipeline._dm_classify_tasks.values() if not t.done()]
    for t in tasks:
        t.cancel()
    waited = tasks + [t for t in pipeline._dm_classify_running if not t.done()]
    if waited:
        await _wait_out(pipeline, waited, drain=drain)


async def _drain_buffers(pipeline) -> None:
    """Разобрать напоследок всё, что осталось в копилках при уходе в OFF.

    Иначе пакет, накопленный за срок ожидания, пропадает молча, и человек
    видит «HR ответил, а статус не двинулся». Разбираются люди разом, а не
    по очереди: пятеро подряд — это полминуты, в которые цикл не отвечает
    ни на остановку, ни на побудку. Сломавшийся разбор одного человека
    остальных не роняет.
    """
    # Ключи снимаются заранее: `classify_and_apply_for_hr` вынимает копилку.
    hr_ids = [hr_id for hr_id, buf in pipeline._dm_classify_buffer.items() if buf]
    if not hr_ids:
        return
    results = await asyncio.gather(
        *(classify_and_apply_for_hr(pipeline, hr_id) for hr_id in hr_ids),
        return_exceptions=True,
    )
    for hr_id, res in zip(hr_ids, results):
        if isinstance(res, Exception):
            logger.exception(
                "drain classify on OFF failed for hr %d", hr_id, exc_info=res,
            )


async def cancel_pending_dm_classifications(
    pipeline, *, drain: bool = False
) -> None:
    """Кенсельнут все висящие debounce-таймеры (бот стопается / OFF /
    shutdown). asyncio.Task.cancel() — это hint, который сработает
    только если task сидит на await. Если он уже прошёл sleep и
    исполняет sync-блок (drain → classify → apply), cancel() — no-op,
    и task продолжит дёргать httpx-клиент / session_factory — которые
    могут уже быть закрыты в shutdown-пути. Поэтому ПОСЛЕ cancel'ов
    ждём с таймаутом, чтобы все живые task'и доработали или
    завершились по cancel'у.

    Edge race во время normal completion: tardy task мог проскочить
    cancel (был в commit'е) и сделать `apply_classification` уже
    ПОСЛЕ pipeline._dm_classify_tasks.clear(). Корректность не нарушается —
    commit прошёл, статус-history-row записан; просто tasks-dict
    некоторое время будет содержать ссылку на завершившийся task,
    пока следующий schedule_dm_classification его не перезапишет.

    ``drain=True`` (OFF transition) — накопленное разбирается напоследок,
    см. :func:`_drain_buffers`. Shutdown путь использует drain=False —
    клиенты/сессии уже закрываются.
    """
    await _cancel_and_wait(pipeline, drain=drain)
    pipeline._dm_classify_tasks.clear()
    if drain and pipeline._shutting_down:
        logger.debug(
            "cancel_pending_dm_classifications: drain=True ignored "
            "because shutdown in progress"
        )
    if drain and not pipeline._shutting_down:
        await _drain_buffers(pipeline)
    pipeline._dm_classify_buffer.clear()
