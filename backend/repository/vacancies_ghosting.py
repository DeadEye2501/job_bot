"""Вакансии, о которых замолчали: срок тишины и гашение по нему.

Живёт своим модулем, потому что предмет свой: статус вакансии
(`vacancy_status`) меняется от того, что кто-то сделал, а здесь — от того, что
не сделал никто. Отсюда и весь счёт отметок жизни: последнее письмо HR,
последняя постановка в нынешний статус, заведение самой строки.
"""

import logging

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.transitions import GHOSTING_ELIGIBLE_FROM
from backend.models import Vacancy
from backend.repository.vacancies_activity import (
    entered_current_status_at,
    last_incoming_subq,
)
from backend.repository.vacancy_status import apply_silence

logger = logging.getLogger(__name__)


async def _silence_candidates(session: AsyncSession):
    """Вакансии, которым срок молчания вообще считается, с их отметками.

    Один заход в базу вместо 1+2N: последние отметки собраны заранее
    подзапросами. Соединение внешнее потому, что у свежей вакансии может не
    быть ни писем, ни истории.

    Из истории берётся смена **в нынешний статус** — отсюда сверка
    `status == Vacancy.status` в соединении: молчание отсчитывается с того
    мига, как вакансия встала туда, где стоит сейчас, а не с любой давней
    смены статуса.
    """
    last_msg_subq = last_incoming_subq()
    return (
        await session.execute(
            select(
                Vacancy,
                last_msg_subq.c.max_at,
                entered_current_status_at(),
            )
            .outerjoin(last_msg_subq, last_msg_subq.c.vid == Vacancy.id)
            .where(Vacancy.status.in_([s for s in GHOSTING_ELIGIBLE_FROM]))
        )
    ).all()


def _last_activity(vacancy: Vacancy, last_msg_at, entered_at):
    """Самая поздняя отметка жизни вакансии; от неё и считается молчание.

    Заведение и вход в нынешний статус есть всегда — второе при отсутствии
    истории и есть заведение, — а письмо может не случиться вовсе.
    """
    timestamps = [vacancy.created_at, entered_at]
    if last_msg_at is not None:
        timestamps.append(last_msg_at)
    return max(timestamps)


async def mark_ghosted_vacancies(
    session: AsyncSession,
    *,
    timeout_days: int,
) -> list[int]:
    """Сканирует Applied/In Progress вакансии и переводит в Ghosting те,
    у которых HR молчит дольше ``timeout_days``.

    «Молчит» означает: ни входящего письма, ни постановки в нынешний
    статус, ни заведения самой вакансии в окне последних ``timeout_days``
    дней — см. :func:`_last_activity` и :func:`_silence_candidates`.

    Возвращает список vacancy_id, переведённых в Ghosting. Caller
    оборачивает в session.begin() и выполняет commit.
    """
    # SQLite + aiosqlite возвращает наивные datetime'ы даже при
    # DateTime(timezone=True), поэтому для Python-side сравнения с
    # v.created_at / max(sent_at) / max(changed_at) cutoff тоже должен
    # быть naive (UTC по конвенции — server_default=func.now()).
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
        days=timeout_days
    )
    affected: list[int] = []
    for v, last_msg_at, entered_at in await _silence_candidates(session):
        if _last_activity(v, last_msg_at, entered_at) >= cutoff:
            continue
        apply_silence(session, v, timeout_days)
        affected.append(v.id)
    return affected
