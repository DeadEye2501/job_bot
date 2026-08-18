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
    """Начало выбранного срока, а для «за всё время» — пустота.

    «Сегодня» считается от начала **местных** суток: полночь человек мерит по
    своим часам. На поясе UTC+4 отсчёт от полуночи UTC начинал бы «сегодня» в
    четыре утра — заведённое ночью в него не попадало бы, зато попадало бы
    вчерашнее с восьми вечера. Остальные сроки скользящие, и им пояс безразличен.
    """
    now = datetime.now(timezone.utc)
    if period == "today":
        here = now.astimezone()
        return here.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(
            timezone.utc
        )
    if period == "week":
        return now - timedelta(days=7)
    if period == "month":
        return now - timedelta(days=30)
    if period == "quarter":
        return now - timedelta(days=90)
    return None  # all-time
