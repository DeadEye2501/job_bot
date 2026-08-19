"""Следствия распределения ответов HR по дням недели.

День берётся по времени, когда HR нажал «отправить», а не когда бот сохранил
сообщение: иначе распределение показывало бы часы работы бота, а не живого
человека.
"""

from datetime import datetime, timedelta, timezone

from backend.repository.stats_responses import get_stats_hr_responses
from tests.dbio import put
from tests.factories import hr_row


def _monday(hour: int = 12) -> datetime:
    """Понедельник на прошлой неделе, наивный по UTC."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    start_of_week = (now - timedelta(days=now.weekday())).replace(
        hour=hour, minute=0, second=0, microsecond=0
    )
    return start_of_week - timedelta(days=7)


def _local_monday_after_midnight() -> datetime:
    """Понедельник, полпервого ночи по часам человека, — как лежит в базе.

    В базе метка наивная и по UTC. Восточнее Гринвича этот же миг приходится
    ещё на воскресенье по UTC, а на календаре человека уже понедельник, и
    именно его он ждёт увидеть в столбике.
    """
    now_local = datetime.now().astimezone()
    monday = (now_local - timedelta(days=now_local.weekday() + 7)).replace(
        hour=0, minute=30, second=0, microsecond=0
    )
    return monday.astimezone(timezone.utc).replace(tzinfo=None)


async def test_the_weekday_is_the_one_on_the_human_calendar(
    session, session_factory, applied
):
    """День недели берётся по местным часам, а не по Гринвичу.

    Ответ, пришедший в первом часу ночи понедельника, человек помнит
    понедельничным. По Гринвичу это ещё воскресенье, и весь столбик
    съезжал на день у всякого, кто живёт не на нулевом поясе.
    """
    hr = hr_row()
    await put(session_factory, hr)
    answered_at = _local_monday_after_midnight()

    await applied(
        answered_at - timedelta(days=2), hr=hr, answered_after=timedelta(days=2)
    )

    got = await get_stats_hr_responses(session, period="all")

    assert got["by_weekday"] == [1, 0, 0, 0, 0, 0, 0]


async def test_the_weekday_comes_from_the_answer(session, session_factory, applied):
    """День недели берётся у ответа, а не у отправки отклика."""
    hr = hr_row()
    await put(session_factory, hr)

    await applied(_monday(), hr=hr, answered_after=timedelta(days=2))

    got = await get_stats_hr_responses(session, period="all")

    assert got["by_weekday"] == [0, 0, 1, 0, 0, 0, 0]
