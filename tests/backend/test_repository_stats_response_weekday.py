"""Следствия распределения ответов HR по дням недели.

День берётся по времени, когда HR нажал «отправить», а не когда бот сохранил
сообщение: иначе распределение показывало бы часы работы бота, а не живого
человека.
"""

from datetime import datetime, timedelta, timezone

from backend.models import VacancyStatus
from backend.repository.stats_summary import get_stats_hr_responses
from tests.dbio import put
from tests.factories import hr_row, message_row, status_history_row, vacancy_row


def _monday(hour: int = 12) -> datetime:
    """Понедельник на прошлой неделе, наивный по UTC."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    start_of_week = (now - timedelta(days=now.weekday())).replace(
        hour=hour, minute=0, second=0, microsecond=0
    )
    return start_of_week - timedelta(days=7)


async def test_the_weekday_comes_from_the_answer(session, session_factory):
    """День недели берётся у ответа, а не у отправки отклика."""
    hr = hr_row()
    await put(session_factory, hr)
    vacancy = vacancy_row(hr_id=hr.id)
    await put(session_factory, vacancy)
    monday = _monday()
    await put(
        session_factory,
        status_history_row(
            vacancy.id, status=VacancyStatus.APPLIED, changed_at=monday
        ),
    )
    await put(
        session_factory,
        message_row(
            hr_id=hr.id,
            vacancy_id=vacancy.id,
            is_incoming=True,
            sent_at=monday + timedelta(days=2),
        ),
    )

    got = await get_stats_hr_responses(session, period="all")

    assert got["by_weekday"] == [0, 0, 1, 0, 0, 0, 0]
