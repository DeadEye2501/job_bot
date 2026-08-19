"""Кирпичи, из которых обе половины экрана статистики собирают свои числа.

Своим модулем, потому что зовущих у каждого несколько и они равноправны:
четыре половины сводки и воронка по каналам. Пока кирпичи лежали у одной из них,
остальные ввозили их через границу модуля — то есть знали про соседа, чтобы
посчитать своё.

Подчёркивания у имён здесь нет нарочно: у объявления, общего для двоих, оно
означало бы «не ввозить», а ввозят его как раз оба.
"""

from datetime import datetime, time, timedelta, timezone

from sqlalchemy import func, select

from backend.models import Vacancy, VacancyStatusHistory
from backend.repository.vacancies_common import PARSED_ONLY


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


def parsed_in_window(since) -> list:
    """Условия «разобранная вакансия, заведённая в окне»; без окна — только разбор.

    Кирпич этот берут трое: дельта числа вакансий, частота технологий и
    ингест по каналам. Набранный порознь, он разъезжался бы молча — три
    числа одного экрана считались бы по трём разным множествам строк.
    """
    conditions = [PARSED_ONLY]
    if since is not None:
        conditions.append(Vacancy.created_at >= since)
    return conditions


def stats_period_since(period: str) -> datetime | None:
    """Начало выбранного срока, а для «за всё время» — пустота.

    «Сегодня» считается от начала **местных** суток: полночь человек мерит по
    своим часам. На поясе UTC+4 отсчёт от полуночи UTC начинал бы «сегодня» в
    четыре утра — заведённое ночью в него не попадало бы, зато попадало бы
    вчерашнее с восьми вечера. Остальные сроки скользящие, и им пояс безразличен.

    Полночь собирается заново из даты, а не получается обнулением часов у
    нынешнего мига: обнуление сохраняет смещение, верное на **сейчас**, а в
    сутки перевода часов оно у полуночи другое, и начало суток съезжало бы
    на час.
    """
    now = datetime.now(timezone.utc)
    if period == "today":
        here = now.astimezone()
        midnight = datetime.combine(here.date(), time.min).astimezone()
        return midnight.astimezone(timezone.utc)
    if period == "week":
        return now - timedelta(days=7)
    if period == "month":
        return now - timedelta(days=30)
    if period == "quarter":
        return now - timedelta(days=90)
    return None  # all-time
