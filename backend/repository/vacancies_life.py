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
    Application,
    Message,
    Screening,
    TrashEvent,
    Vacancy,
    VacancyContact,
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
    session: AsyncSession, vacancy: Vacancy | None, reason: str | None
) -> None:
    """Отметить объявление мусором. Одно объявление — одна отметка.

    Пишется до удаления строки вакансии: после него знать, сколько мусора
    прислал источник, было бы не из чего. Объявление узнают по номеру на
    источнике — сообщения в канале или на агрегаторе: тот же пост приходит на
    разбор второй раз после сброса курсора канала, то же объявление агрегатора —
    на следующем обходе, и без сверки числа росли бы от каждого повтора. Без
    номера сверить не с чем, и отметка пишется всегда.
    """
    mark = TrashEvent(reason=reason)
    if vacancy is not None:
        mark.source_channel_id = vacancy.source_channel_id
        mark.source_msg_id = vacancy.source_msg_id
        mark.source_aggregator_id = vacancy.source_aggregator_id
        mark.source_key = vacancy.source_key
    if not await _trash_noted(session, mark):
        session.add(mark)


async def source_trashed(session: AsyncSession, aggregator_id: int, key: str) -> bool:
    """Отмечено ли мусором объявление с этим номером на этом агрегаторе."""
    return await _marked(
        session,
        TrashEvent.source_aggregator_id == aggregator_id,
        TrashEvent.source_key == key,
    )


async def source_seen(session: AsyncSession, aggregator_id: int, key: str) -> bool:
    """Видели ли номер на этом агрегаторе: вакансия с ним заведена или удалена как мусор."""
    stored = await session.scalar(select(Vacancy.id).where(
        Vacancy.source_aggregator_id == aggregator_id, Vacancy.source_key == key
    ).limit(1))
    return stored is not None or await source_trashed(session, aggregator_id, key)


async def _trash_noted(session: AsyncSession, mark: TrashEvent) -> bool:
    """Отмечено ли это объявление мусором раньше."""
    if mark.source_key is not None:
        return await source_trashed(session, mark.source_aggregator_id, mark.source_key)
    if mark.source_msg_id is None:
        return False
    return await _marked(
        session,
        TrashEvent.source_channel_id == mark.source_channel_id,
        TrashEvent.source_msg_id == mark.source_msg_id,
    )


async def _marked(session: AsyncSession, *same) -> bool:
    return (await session.scalar(select(TrashEvent.id).where(*same).limit(1))) is not None


async def delete_vacancy(session: AsyncSession, vacancy_id: int) -> bool:
    """Hard-delete a vacancy + its history + its events + its contacts + its
    applications with their screening.

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
    applications = select(Application.id).where(Application.vacancy_id == vacancy_id)
    await session.execute(
        delete(Screening).where(Screening.application_id.in_(applications))
    )
    await session.execute(delete(Application).where(Application.vacancy_id == vacancy_id))
    await session.execute(
        delete(VacancyContact).where(VacancyContact.vacancy_id == vacancy_id)
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
        "Deleted vacancy %d (msgs detached, dependent rows purged)", vacancy_id
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
