"""Скорость ответа HR: сколько ждали, кто не ответил и в какие дни отвечают."""

from datetime import datetime, timezone
from statistics import median

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.funnel import RESPONDED, percent_or_none
from backend.models import Vacancy, VacancyStatus, VacancyStatusHistory
from backend.repository.stats_common import (
    first_transition_subq,
    stats_period_since,
    status_cond,
)
from backend.repository.vacancies_common import PARSED_ONLY


async def _applied_in_period(
    session: AsyncSession, since: datetime | None
) -> dict[int, datetime]:
    """Когда откликнулись — по вакансиям, отклик на которые попал в окно.

    Берём разобранные вакансии, у которых ПЕРВЫЙ переход в Applied случился
    внутри окна (по `VacancyStatusHistory.changed_at`): ровно те отклики,
    которые мы делали в этот период. Отбор по разбору тот же, что у соседних
    ступеней экрана — считая по своему множеству, ступень разводила бы числа
    двух экранов молча.
    """
    first_applied_subq = first_transition_subq(VacancyStatus.APPLIED)
    where_clauses = [PARSED_ONLY]
    if since is not None:
        where_clauses.append(first_applied_subq.c.first_at >= since)
    rows = (
        await session.execute(
            select(first_applied_subq.c.vid, first_applied_subq.c.first_at)
            .join(Vacancy, Vacancy.id == first_applied_subq.c.vid)
            .where(*where_clauses)
        )
    ).all()
    return {vid: applied_at for vid, applied_at in rows}


async def _first_response_at(
    session: AsyncSession, applied_map: dict[int, datetime]
) -> dict[int, datetime]:
    """Когда ответили впервые — первый переход в ответный статус не раньше отклика.

    Ответ меряется сменой статуса, а не перепиской: откликнуться можно и на
    сайте, и по почте, и ответ оттуда приложение не видит, а смену статуса
    видит всегда. Ответный — любой статус `RESPONDED`: вакансия, сразу
    ушедшая из отклика в тест или к офферу, тоже получила ответ.

    Одним запросом, а не по вакансии: выборки маленькие — десятки-сотни, —
    и группировка в Python дешевле N обращений к базе.
    """
    rows = (
        await session.execute(
            select(VacancyStatusHistory.vacancy_id, VacancyStatusHistory.changed_at)
            .where(
                VacancyStatusHistory.vacancy_id.in_(applied_map.keys()),
                status_cond(RESPONDED),
            )
        )
    ).all()
    first_by_vid: dict[int, datetime] = {}
    for vid, changed_at in rows:
        # Одна секунда с откликом — ещё ответ: метки секундные, а ответа
        # раньше отклика не бывает.
        if changed_at < applied_map[vid]:
            continue
        cur = first_by_vid.get(vid)
        if cur is None or changed_at < cur:
            first_by_vid[vid] = changed_at
    return first_by_vid


def _local_weekday(stamp: datetime) -> int:
    """День недели метки по часам человека (Пн=0 … Вс=6).

    Метка наивная и по UTC — так её кладёт база. Считай день прямо по ней, и
    ответ, пришедший в первом часу ночи понедельника, встал бы в столбик
    воскресенья у всякого, кто живёт восточнее Гринвича.
    """
    return stamp.replace(tzinfo=timezone.utc).astimezone().weekday()


def _weekdays_and_waits(
    applied_map: dict[int, datetime], first_resp_by_vid: dict[int, datetime]
) -> tuple[list[int], list[float]]:
    """Ответы по дням недели (Пн=0 … Вс=6) и сроки ожидания в секундах.

    Отрицательного срока здесь не бывает: в `first_resp_by_vid` попадают
    только переходы не раньше нашего отклика, и это условие отбора, а не удача.
    """
    by_weekday = [0, 0, 0, 0, 0, 0, 0]
    waits: list[float] = []
    for vid, applied_at in applied_map.items():
        resp_ts = first_resp_by_vid.get(vid)
        if resp_ts is None:
            continue
        by_weekday[_local_weekday(resp_ts)] += 1
        waits.append((resp_ts - applied_at).total_seconds())
    return by_weekday, waits


async def get_stats_hr_responses(
    session: AsyncSession, *, period: str
) -> dict:
    """HR-response-time + weekday-распределение ответов.

    Метрики:
      - by_weekday: распределение первого ответного перехода по дням недели
        (0=Пн … 6=Вс)
      - median_seconds: median(первый ответный переход − applied_at) среди
        тех, кто ответил
      - no_response_pct: процент applied вакансий БЕЗ first-response
      - applied_count / responded_count: голые числа
    """
    applied_map = await _applied_in_period(session, stats_period_since(period))
    # Пустая связка до базы не идёт: спрашивать переходы по пустому перечню
    # вакансий не о чем. Отдельного ответа у неё нет — все шесть чисел
    # выходят теми же правилами, и пустой перечень даёт нули и пустоты сам.
    first_resp_by_vid = (
        await _first_response_at(session, applied_map) if applied_map else {}
    )
    by_weekday, waits = _weekdays_and_waits(applied_map, first_resp_by_vid)
    applied_count = len(applied_map)
    responded_count = len(first_resp_by_vid)
    return {
        "period": period,
        "by_weekday": by_weekday,
        "median_seconds": float(median(waits)) if waits else None,
        "no_response_pct": percent_or_none(
            applied_count - responded_count, applied_count
        ),
        "applied_count": applied_count,
        "responded_count": responded_count,
    }
