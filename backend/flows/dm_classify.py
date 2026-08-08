"""Отложенный разбор накопленной переписки с HR."""

import logging
import asyncio

from sqlalchemy import select

from backend.domain.transitions import is_terminal_for_auto
from backend.llm.hr_reply import classify_hr_reply
from backend.models import Vacancy
from backend.repository.vacancies_life import apply_classification

logger = logging.getLogger(__name__)


def update_dm_buffer_text(pipeline, hr_id: int, msg_id: int, new_text: str) -> None:
    """HR отредактировал сообщение пока оно сидит в debounce-буфере —
    обновим текст, чтобы LLM-классификатор видел свежее содержимое."""
    buf = pipeline._dm_classify_buffer.get(hr_id)
    if not buf:
        return
    for item in buf:
        if item["msg_id"] == msg_id:
            item["text"] = new_text or ""
            break


def remove_dm_buffer_msg(pipeline, hr_id: int, msg_id: int) -> None:
    """HR удалил сообщение пока оно сидит в debounce-буфере — выкинем
    его из burst'а, чтобы не учитывать в классификации."""
    buf = pipeline._dm_classify_buffer.get(hr_id)
    if not buf:
        return
    pipeline._dm_classify_buffer[hr_id] = [
        item for item in buf if item["msg_id"] != msg_id
    ]
    if not pipeline._dm_classify_buffer[hr_id]:
        pipeline._dm_classify_buffer.pop(hr_id, None)


def schedule_dm_classification(
    pipeline,
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
    if pipeline._shutting_down:
        return
    if not text:
        # Медиа-only без подписи нечем классифицировать. Пропускаем
        # тихо — само сообщение уже в БД.
        return
    buf = pipeline._dm_classify_buffer.setdefault(hr_id, [])
    buf.append({"vacancy_id": vacancy_id, "msg_id": msg_id, "text": text})
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
    await classify_and_apply_for_hr(pipeline, hr_id)


async def classify_and_apply_for_hr(pipeline, hr_id: int) -> None:
    """Drain burst-буфера для hr_id: один LLM-вызов на накопленный
    пакет → apply_classification. Используется и из debounce-тика,
    и из drain-on-OFF в `cancel_pending_dm_classifications`.
    """
    # Re-check blacklist: HR мог попасть туда между process_dm-time
    # (когда мы пропустили входящее в фильтре) и фактическим debounce-
    # тиком. process_dm уже не пишет такие сообщения в буфер, но если
    # blacklist взвели за время burst'а — текущий накопленный пакет
    # тоже надо отбросить, не классифицируя.
    async with pipeline._session_factory() as session:
        from backend.repository.hr_card import _hr_blacklist_value
        from backend.models import HR
        hr_row = await session.get(HR, hr_id)
        bl_value = (
            await _hr_blacklist_value(session, hr_row) if hr_row else None
        )
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
    # Склеиваем тексты с двойным переносом — чтобы LLM видела границы
    # отдельных сообщений и могла выбрать самый продвинутый сигнал
    # (Offer > Invitation > Test > Decline > Answered) на ВСЕМ пакете.
    text = "\n\n".join(item["text"] for item in buf)
    last = buf[-1]
    vacancy_id = last["vacancy_id"]
    msg_id = last["msg_id"]
    # Re-check state-machine: статус мог уйти в терминальный за время
    # debounce-окна (например, юзер вручную выставил Decline), и
    # классифицировать burst уже бессмысленно — apply_classification
    # всё равно отбьёт `should_apply_status`. Лучше срезать здесь —
    # экономим LLM-вызов.
    async with pipeline._session_factory() as session:
        v_status = await session.scalar(
            select(Vacancy.status).where(Vacancy.id == vacancy_id)
        )
    if v_status is not None and is_terminal_for_auto(v_status):
        logger.info(
            "vacancy %s: status=%s terminal for auto, "
            "drop debounced burst (hr %d, %d msgs)",
            vacancy_id, v_status.value, hr_id, len(buf),
        )
        return
    try:
        async with pipeline._dm_classify_semaphore:
            classification = await classify_hr_reply(
                text, v_status, pipeline._lm_client, pipeline._lm_chat_model
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
    async with pipeline._session_factory() as session:
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
    if pipeline.on_vacancies_changed is not None:
        try:
            pipeline.on_vacancies_changed()
        except Exception:
            logger.exception("on_vacancies_changed hook failed")


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

    ``drain=True`` (OFF transition) — после cancel'ов проходим по
    каждому непустому буферу и делаем финальную классификацию: иначе
    burst, накопленный за debounce-окном, пропадает молча и юзер
    получает «вакансия в Answered, но статус не двинулся». Shutdown
    путь использует drain=False — клиенты/сессии уже закрываются.
    """
    tasks = [t for t in pipeline._dm_classify_tasks.values() if not t.done()]
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
    pipeline._dm_classify_tasks.clear()
    if drain and pipeline._shutting_down:
        logger.debug(
            "cancel_pending_dm_classifications: drain=True ignored "
            "because shutdown in progress"
        )
    if drain and not pipeline._shutting_down:
        # Snapshot keys — classify_and_apply_for_hr pop'ает буфер.
        # Параллелим: 5 HR'ов × 3-5s LLM-RTT последовательно = ~25s
        # стола в OFF transition, в течение которого run-loop не
        # реагирует на stop_event/wake. asyncio.gather + return_exceptions
        # — пусть один сломанный classify не валит остальные.
        hr_ids = [hr_id for hr_id, buf in pipeline._dm_classify_buffer.items() if buf]
        if hr_ids:
            results = await asyncio.gather(
                *(classify_and_apply_for_hr(pipeline, hr_id) for hr_id in hr_ids),
                return_exceptions=True,
            )
            for hr_id, res in zip(hr_ids, results):
                if isinstance(res, Exception):
                    logger.exception(
                        "drain classify on OFF failed for hr %d",
                        hr_id, exc_info=res,
                    )
    pipeline._dm_classify_buffer.clear()
