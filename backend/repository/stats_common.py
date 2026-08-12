"""Кирпичи, из которых обе половины экрана статистики собирают свои числа.

Своим модулем, а не половиной `stats_summary`, потому что зовущих у них двое
и они равноправны: сводка и воронка по каналам. Пока кирпичи лежали у сводки,
воронка ввозила их через границу модуля — то есть знала про соседний экран,
чтобы посчитать свой.

Подчёркивания у имён здесь нет нарочно: у объявления, общего для двоих, оно
означало бы «не ввозить», а ввозят его как раз оба.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from backend.models import VacancyStatusHistory


def status_cond(statuses):
    """Условие «статус перехода тот самый». Принимает и одиночный статус,
    и любой набор — звать с одним значением удобнее, чем с набором из него.
    """
    return (
        VacancyStatusHistory.status.in_(statuses)
        if isinstance(statuses, (frozenset, set, list, tuple))
        else VacancyStatusHistory.status == statuses
    )


def first_transition_subq(statuses):
    """Подзапрос «когда вакансия впервые перешла в эти статусы»: пара
    из номера вакансии и самого раннего времени перехода.
    """
    return (
        select(
            VacancyStatusHistory.vacancy_id.label("vid"),
            func.min(VacancyStatusHistory.changed_at).label("first_at"),
        )
        .where(status_cond(statuses))
        .group_by(VacancyStatusHistory.vacancy_id)
        .subquery()
    )


def stats_period_since(period: str) -> datetime | None:
    """Convert UI period code to a since-timestamp, or None for 'all'."""
    now = datetime.now(timezone.utc)
    if period == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "week":
        return now - timedelta(days=7)
    if period == "month":
        return now - timedelta(days=30)
    if period == "quarter":
        return now - timedelta(days=90)
    return None  # all-time
