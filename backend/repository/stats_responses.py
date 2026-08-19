"""Скорость ответа HR: сколько ждали, кто не ответил и в какие дни пишут."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.funnel import percent_or_none
from backend.models import Message, Vacancy, VacancyStatus
from backend.repository.stats_common import (
    first_transition_subq,
    stats_period_since,
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
    """Когда HR ответил впервые — первое входящее позже нашего отклика.

    Берём `Message.sent_at` (когда HR нажал «отправить»), а не `created_at`
    (когда наш бот сохранил): день недели должен отражать, когда живой HR.
    Одним запросом, а не по вакансии: выборки маленькие — десятки-сотни, —
    и группировка в Python дешевле N обращений к базе.
    """
    rows = (
        await session.execute(
            select(Message.vacancy_id, Message.sent_at)
            .where(
                Message.vacancy_id.in_(applied_map.keys()),
                Message.is_incoming.is_(True),
                Message.is_deleted.is_(False),
            )
        )
    ).all()
    first_by_vid: dict[int, datetime] = {}
    for vid, sent_at in rows:
        if sent_at is None:
            continue
        applied_at = applied_map.get(vid)
        if applied_at is None or sent_at <= applied_at:
            continue
        cur = first_by_vid.get(vid)
        if cur is None or sent_at < cur:
            first_by_vid[vid] = sent_at
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
    только письма позже нашего отклика, и это условие отбора, а не удача.
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


def _median(values: list[float]) -> float | None:
    """Середина ряда; на пустом ряду середины нет."""
    if not values:
        return None
    ordered = sorted(values)
    n = len(ordered)
    if n % 2 == 1:
        return float(ordered[n // 2])
    return (ordered[n // 2 - 1] + ordered[n // 2]) / 2


async def get_stats_hr_responses(
    session: AsyncSession, *, period: str
) -> dict:
    """HR-response-time + weekday-распределение ответов.

    Метрики:
      - by_weekday: распределение first-response.sent_at по дням недели
        (0=Пн … 6=Вс)
      - median_seconds: median(first_response_sent_at − applied_at) среди
        тех, кто ответил
      - no_response_pct: процент applied вакансий БЕЗ first-response
      - applied_count / responded_count: голые числа
    """
    applied_map = await _applied_in_period(session, stats_period_since(period))
    # Пустая связка до базы не идёт: спрашивать письма по пустому перечню
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
        "median_seconds": _median(waits),
        "no_response_pct": percent_or_none(
            applied_count - responded_count, applied_count
        ),
        "applied_count": applied_count,
        "responded_count": responded_count,
    }
