"""Верхняя строка экрана статистики: пять счётчиков и дельта у каждого."""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.funnel import IN_PROGRESS_STEP
from backend.models import Vacancy, VacancyStatus, VacancyStatusHistory
from backend.repository.stats_common import (
    first_transition_subq,
    parsed_in_window,
    stats_period_since,
    status_cond,
)
from backend.repository.vacancies_common import PARSED_ONLY


async def _ever_in(session: AsyncSession, statuses) -> int:
    """Сколько разобранных вакансий когда-либо побывало в этих статусах.

    Соединение с вакансией тут не ради полей, а ради `is_parsed`: без него
    ступени воронки считались бы по всем строкам истории, включая
    неразобранные, и «откликнулись» выходило бы больше, чем «всего».
    """
    return int((await session.execute(
        select(func.count(func.distinct(VacancyStatusHistory.vacancy_id)))
        .join(Vacancy, Vacancy.id == VacancyStatusHistory.vacancy_id)
        .where(status_cond(statuses), PARSED_ONLY)
    )).scalar_one())


async def _first_in_period(
    session: AsyncSession, statuses, since: datetime
) -> int:
    """Сколько вакансий впервые дошло до этих статусов внутри окна."""
    sub = first_transition_subq(statuses)
    return int((await session.execute(
        select(func.count(sub.c.vid))
        .join(Vacancy, Vacancy.id == sub.c.vid)
        .where(sub.c.first_at >= since, PARSED_ONLY)
    )).scalar_one())


async def _kpi_totals(session: AsyncSession) -> dict:
    """Лайфтайм-счётчики верхней строки экрана.

    Все, кроме `total`, считаются по истории — вакансии, у которых КОГДА-ЛИБО
    был переход в статус. Счётчики от этого монотонные: ручной откат статуса
    назад их не уменьшает.
    """
    return {
        "total": int((await session.execute(
            select(func.count(Vacancy.id)).where(PARSED_ONLY)
        )).scalar_one()),
        "applied_total": await _ever_in(session, VacancyStatus.APPLIED),
        "in_progress_total": await _ever_in(session, IN_PROGRESS_STEP),
        "offer_total": await _ever_in(session, VacancyStatus.OFFER),
        "decline_total": await _ever_in(session, VacancyStatus.DECLINE),
    }


async def _kpi_deltas(session: AsyncSession, since: datetime | None) -> dict:
    """Дельты за окно; без окна дельт нет вовсе, и это не ноль, а пусто.

    У `total` окно считается по `created_at`, у остальных — по первому
    переходу в статус: ступень принадлежит тому окну, в котором её прошли.
    """
    if since is None:
        return {
            "total_period": None,
            "applied_period": None,
            "in_progress_period": None,
            "offer_period": None,
            "decline_period": None,
        }
    return {
        "total_period": int((await session.execute(
            select(func.count(Vacancy.id)).where(*parsed_in_window(since))
        )).scalar_one()),
        "applied_period": await _first_in_period(
            session, VacancyStatus.APPLIED, since
        ),
        "in_progress_period": await _first_in_period(
            session, IN_PROGRESS_STEP, since
        ),
        "offer_period": await _first_in_period(
            session, VacancyStatus.OFFER, since
        ),
        "decline_period": await _first_in_period(
            session, VacancyStatus.DECLINE, since
        ),
    }


async def get_stats_kpi(
    session: AsyncSession, *, period: str
) -> dict:
    """Top-row KPIs для экрана Statistics: 5 счётчиков с дельтой за period.

    - total: лайфтайм count всех parsed-вакансий.
    - applied_total: когда-либо были в Applied.
    - in_progress_total: когда-либо доходили до середины воронки —
      Invitation, Test или In Progress (`domain/funnel.IN_PROGRESS_STEP`).
    - offer_total: когда-либо доходили до Offer.
    - decline_total: когда-либо были в Decline.

    Рядом с каждым идёт своя дельта за окно — `total_period`,
    `applied_period`, `in_progress_period`, `offer_period`, `decline_period`;
    чем она считается и почему при `period="all"` это пустота, а не ноль, —
    :func:`_kpi_deltas`.
    """
    since = stats_period_since(period)
    return {
        "period": period,
        **await _kpi_totals(session),
        **await _kpi_deltas(session, since),
    }
