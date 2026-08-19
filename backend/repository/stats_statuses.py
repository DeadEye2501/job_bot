"""Разбивка вакансий по нынешним статусам за выбранный срок."""

from sqlalchemy.ext.asyncio import AsyncSession

from backend.repository.stats_common import stats_period_since
from backend.repository.vacancies_activity import entered_current_status_at
from backend.repository.vacancies_common import PARSED_ONLY, count_by_status


async def get_stats_status_breakdown(
    session: AsyncSession, *, period: str
) -> dict:
    """Сколько вакансий в каком статусе сейчас; за период или за всё время.

    Считается нынешний статус, а не пройденные: это снимок «где всё лежит
    сейчас», а не «через что прошло». Окно при этом отсекает по времени, в
    которое вакансия встала туда, где стоит (:func:`entered_current_status_at`),
    — то есть по переходу, как и дельты в шапке того же экрана (различие двух
    счётов описано у самой :func:`entered_current_status_at`: шапка берёт
    первый переход, а здесь последний в нынешний). Считай оно по дате
    появления, соседние карточки противоречили бы друг другу.
    """
    since = stats_period_since(period)
    conditions = [PARSED_ONLY]
    if since is not None:
        conditions.append(entered_current_status_at() >= since)
    by_status = await count_by_status(session, *conditions)
    return {
        "period": period,
        "counts": {status.value: n for status, n in by_status.items()},
    }
