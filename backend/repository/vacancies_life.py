"""Что случается с вакансией после того, как её завели, кроме смены статуса.

Само заведение живёт не здесь, а в конвейере (`flows/ingest`): строка
`Vacancy(...)` собирается там и только там. Обещай докстрока «от заведения»,
читатель искал бы запись строки в этом модуле и не нашёл.

Остальная её жизнь: отметки в ленте, отметки о мусоре, перевод вакансий на
другого владельца, удаление. Перечислять их фразой смысла нет — предмет один,
вакансия, и меняется он по-разному.

Смена статуса отсюда ушла в `vacancy_status`. У неё своя ответственность —
решить, позволен ли переход, — и держать её рядом с удалением строки значило
держать в одном модуле два.
"""

import logging

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import (
    Message,
    TrashEvent,
    Vacancy,
    VacancyEvent,
    VacancyStatusHistory,
)

logger = logging.getLogger(__name__)


async def repoint_vacancies(
    session: AsyncSession, column, *, absorbed_id: int, survivor_id: int | None
) -> int:
    """Переписывает владельца вакансий: с уходящей строки на названную.

    Названная — либо оставшаяся при слиянии, либо `None` при удалении: у
    вакансии нет владельца, и она переживает удаление человека, компании и
    канала. Правило одно, и раньше оно было выписано пятью телами — двумя
    слияниями и тремя удалениями.

    Отметка о мусоре при удалении канала отвязывается **своим** запросом и
    сюда не переводится: это другая таблица, а объявление держит одну —
    вакансии. Второй довод-колонка сделал бы его «переписать владельца у
    чего угодно», то есть чужим оборотом вокруг `update`.

    Возвращает число переехавших — его пишут в журнал: и слияние, и удаление
    необратимы, и по записи потом видно, скольких это задело.
    """
    return (
        await session.execute(
            update(Vacancy).where(column == absorbed_id).values({column: survivor_id})
        )
    ).rowcount or 0


async def record_trash_event(
    session: AsyncSession,
    *,
    source_channel_id: int | None,
    source_msg_id: int | None,
    reason: str | None,
) -> None:
    """Записать факт «пост из канала классифицирован как trash».
    Используется ДО удаления Vacancy-ряда (в auto-ingest режиме), чтобы
    трекать «сколько мусора прислал канал» — иначе после delete этой
    информации в БД не остаётся. Caller оборачивает в session.begin().

    Один пост — одна отметка. Тот же пост приходит на разбор второй раз после
    сброса курсора канала, и без этой проверки числа «сколько мусора прислал
    канал» росли бы от каждого сброса, ничего нового не узнав.
    """
    if source_msg_id is not None and await _trash_noted(
        session, source_channel_id, source_msg_id
    ):
        return
    session.add(TrashEvent(
        source_channel_id=source_channel_id,
        source_msg_id=source_msg_id,
        reason=reason,
    ))


async def _trash_noted(
    session: AsyncSession, source_channel_id: int | None, source_msg_id: int
) -> bool:
    """Отмечен ли этот пост мусором раньше."""
    return (
        await session.scalar(
            select(TrashEvent.id).where(
                TrashEvent.source_channel_id == source_channel_id,
                TrashEvent.source_msg_id == source_msg_id,
            ).limit(1)
        )
    ) is not None


async def delete_vacancy(session: AsyncSession, vacancy_id: int) -> bool:
    """Hard-delete a vacancy + its history + its events.

    ``message.vacancy_id`` is nullified rather than deleted so the chat
    history stays intact (the user might still want to see the conversation
    with the HR after the vacancy was wiped). Returns False if the vacancy
    doesn't exist.

    Caller wraps in ``session.begin()``.
    """
    vacancy = await session.get(Vacancy, vacancy_id)
    if vacancy is None:
        return False
    await session.execute(
        update(Message)
        .where(Message.vacancy_id == vacancy_id)
        .values(vacancy_id=None)
    )
    await session.execute(
        delete(VacancyStatusHistory).where(
            VacancyStatusHistory.vacancy_id == vacancy_id
        )
    )
    await session.execute(
        delete(VacancyEvent).where(VacancyEvent.vacancy_id == vacancy_id)
    )
    await session.delete(vacancy)
    await session.flush()
    logger.info(
        "Deleted vacancy %d (msgs detached, history+events purged)", vacancy_id
    )
    return True


async def add_vacancy_event(
    session: AsyncSession,
    vacancy_id: int,
    kind: str,
    payload: dict | None = None,
) -> VacancyEvent:
    """Append a non-status event to the timeline (parsed, ingested, rerun, ...).

    Status changes go to ``vacancy_status_history`` instead. Caller wraps
    in ``session.begin()``.
    """
    event = VacancyEvent(
        vacancy_id=vacancy_id,
        kind=kind,
        payload=(payload or None),
    )
    session.add(event)
    await session.flush()
    return event
