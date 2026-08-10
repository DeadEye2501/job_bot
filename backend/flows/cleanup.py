"""Удаление вакансий и гашение по сроку молчания."""

import logging

from backend.repository.vacancies_life import delete_vacancy as repo_delete_vacancy

from backend.flows import embeddings
from backend.notify import fire

logger = logging.getLogger(__name__)


async def check_ghosting_timeouts(pipeline) -> int:
    """Сканирует Applied/In Progress вакансии и переводит в Ghosting
    те, по которым HR молчит дольше GHOSTING_TIMEOUT_DAYS.

    Дёргается из Bot.run loop'а раз в poll-tick (DM_ONLY и FULL —
    в OFF не запускается, бот считается «на паузе»). Стоимость
    низкая: только Applied/In Progress попадают в шорт-лист, для
    каждой 2 SQL-запроса (max(message), max(history)). Если
    кандидатов нет — ранний return.
    """
    from backend.domain.transitions import GHOSTING_TIMEOUT_DAYS
    from backend.repository.vacancies_life import mark_ghosted_vacancies

    try:
        async with pipeline._session_factory() as session:
            async with session.begin():
                affected = await mark_ghosted_vacancies(
                    session, timeout_days=GHOSTING_TIMEOUT_DAYS,
                )
    except Exception:
        logger.exception("check_ghosting_timeouts failed")
        return 0
    if affected:
        logger.info(
            "ghosting timer: marked %d vacancies (ids=%s)",
            len(affected), affected,
        )
        fire(pipeline.on_vacancies_changed, "on_vacancies_changed")
    return len(affected)


async def delete_vacancy(pipeline, vacancy_id: int) -> None:
    # Route through the public repository delete so children
    # (vacancy_status_history, vacancy_event) are explicitly cleaned up
    # — SQLite has FK enforcement off in this engine, so a plain
    # session.delete(vacancy) would leave orphan rows.
    async with pipeline._session_factory() as session:
        await repo_delete_vacancy(session, vacancy_id)
        await session.commit()
    embeddings.drop_embedding(pipeline, vacancy_id)
    logger.info("vacancy %d: deleted from DB and embedding cache", vacancy_id)
    # Vacancy_count у HR/Company изменился — пушим refresh.
    pipeline._fire_contacts_changed()
    pipeline._fire_vacancies_changed()


async def delete_vacancy_as_trash(
    pipeline, vacancy_id: int, reason: str | None
) -> None:
    """Auto-ingest trash deletion: ДО delete пишем строку в TrashEvent,
    чтобы потом было что показывать в per-channel статистике (без этого
    канал «прислал N мусора» не посчитать — Vacancy-ряд исчезает совсем).
    Channel/msg-id берём из самой вакансии, всё в одной транзакции.
    """
    from backend.repository.vacancies_life import record_trash_event
    from backend.models import Vacancy as _V
    async with pipeline._session_factory() as session:
        v = await session.get(_V, vacancy_id)
        channel_id = v.source_channel_id if v is not None else None
        msg_id = v.source_msg_id if v is not None else None
        await record_trash_event(
            session,
            source_channel_id=channel_id,
            source_msg_id=msg_id,
            reason=reason,
        )
        await repo_delete_vacancy(session, vacancy_id)
        await session.commit()
    embeddings.drop_embedding(pipeline, vacancy_id)
    logger.info(
        "vacancy %d: deleted as trash (event recorded for channel=%s)",
        vacancy_id, channel_id,
    )
    pipeline._fire_contacts_changed()
    pipeline._fire_vacancies_changed()
