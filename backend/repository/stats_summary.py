"""Сводные числа для экрана статистики."""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.scoring import build_skill_lookup
from backend.domain.skill_names import skill_key
from backend.models import Message, Vacancy, VacancyStatus, VacancyStatusHistory
from backend.repository.profile import list_skills
from backend.repository.stats_common import (
    first_transition_subq,
    stats_period_since,
    status_cond,
)
from backend.repository.vacancies_common import PARSED_ONLY, count_by_status


async def get_stats_kpi(
    session: AsyncSession, *, period: str
) -> dict:
    """Top-row KPIs для экрана Statistics: 5 счётчиков с дельтой за period.

    Все KPI кроме total — history-based (distinct vacancy_id, у которых
    КОГДА-ЛИБО был переход в соответствующий статус). Это монотонно
    растущие счётчики: ручной флип статуса назад не уменьшает их.

    - total: лайфтайм count всех parsed-вакансий.
    - applied_total: когда-либо были в Applied.
    - in_progress_total: когда-либо доходили до Invitation или Test.
    - offer_total: когда-либо доходили до Offer.
    - decline_total: когда-либо были в Decline.

    Дельты — `*_period`: для total — created_at в окне; для остальных —
    первый переход в соответствующий статус (min(changed_at)) в окне.
    """
    since = stats_period_since(period)

    in_progress_set = {VacancyStatus.INVITATION, VacancyStatus.TEST}

    base_filter = [PARSED_ONLY]

    total = int((await session.execute(
        select(func.count(Vacancy.id)).where(*base_filter)
    )).scalar_one())

    async def _ever_in(statuses) -> int:
        """Сколько разобранных вакансий когда-либо побывало в этих статусах.

        Соединение с вакансией тут не ради полей, а ради `is_parsed`: без
        него ступени воронки считались бы по всем строкам истории, включая
        неразобранные, и «откликнулись» выходило бы больше, чем «всего».
        """
        return int((await session.execute(
            select(func.count(func.distinct(VacancyStatusHistory.vacancy_id)))
            .join(Vacancy, Vacancy.id == VacancyStatusHistory.vacancy_id)
            .where(status_cond(statuses), *base_filter)
        )).scalar_one())

    applied_total = await _ever_in(VacancyStatus.APPLIED)
    in_progress_total = await _ever_in(in_progress_set)
    offer_total = await _ever_in(VacancyStatus.OFFER)
    decline_total = await _ever_in(VacancyStatus.DECLINE)

    if since is not None:
        period_filter = [*base_filter, Vacancy.created_at >= since]
        total_period = int((await session.execute(
            select(func.count(Vacancy.id)).where(*period_filter)
        )).scalar_one())

        async def _first_in_period(statuses) -> int:
            sub = first_transition_subq(statuses)
            return int((await session.execute(
                select(func.count(sub.c.vid))
                .join(Vacancy, Vacancy.id == sub.c.vid)
                .where(sub.c.first_at >= since, *base_filter)
            )).scalar_one())

        applied_period = await _first_in_period(VacancyStatus.APPLIED)
        in_progress_period = await _first_in_period(in_progress_set)
        offer_period = await _first_in_period(VacancyStatus.OFFER)
        decline_period = await _first_in_period(VacancyStatus.DECLINE)
    else:
        total_period = applied_period = decline_period = None
        in_progress_period = offer_period = None

    return {
        "period": period,
        "total": total,
        "applied_total": applied_total,
        "in_progress_total": in_progress_total,
        "offer_total": offer_total,
        "decline_total": decline_total,
        "total_period": total_period,
        "applied_period": applied_period,
        "in_progress_period": in_progress_period,
        "offer_period": offer_period,
        "decline_period": decline_period,
    }


async def get_stats_status_breakdown(
    session: AsyncSession, *, period: str
) -> dict:
    """Counts по всем статусам за период (или lifetime для 'all').
    Используется для funnel-карточки и all-status-сounters.
    """
    since = stats_period_since(period)
    conditions = [PARSED_ONLY]
    if since is not None:
        conditions.append(Vacancy.created_at >= since)
    by_status = await count_by_status(session, *conditions)
    return {
        "period": period,
        "counts": {status.value: n for status, n in by_status.items()},
    }


async def get_stats_skills(
    session: AsyncSession, *, period: str, limit: int = 27, min_count: int = 2,
) -> dict:
    """Топ-N технологий из `Vacancy.stack` за period с маркировкой
    «есть в моём профиле».

    - Считаем частоту по канону ``skill_key`` (одна технология = один
      счётчик, как бы её ни написали: «Python» / «python» / «PYTHON»,
      «Docker-Compose» / «docker compose»).
    - Дедупликация в рамках одной вакансии: «Python» в стеке два раза
      = +1, не +2.
    - mine = canon ∈ profile_set, где profile_set — ключи name и aliases
      всех `ProfileSkill`.
    - Фильтруем шум: показываем теги с count >= ``min_count`` (по умолч. 2).
      Топ-N по count desc, тай-брейкер casefold.
    """
    since = stats_period_since(period)
    base_filter = [PARSED_ONLY, Vacancy.stack.is_not(None)]
    if since is not None:
        base_filter.append(Vacancy.created_at >= since)

    # Тот же ключ, что и у баллов: иначе один навык считался бы здесь
    # своим, а в оценке вакансии чужим. И тот же читатель анкеты — иначе
    # «свой» на этом экране решался бы по своему набору строк.
    profile_set = build_skill_lookup(await list_skills(session))

    rows = (
        await session.scalars(select(Vacancy.stack).where(*base_filter))
    ).all()
    counts: dict[str, int] = {}
    canon_by_key: dict[str, str] = {}
    for stack in rows:
        if not isinstance(stack, list):
            continue
        seen_in_row: set[str] = set()
        for item in stack:
            if not isinstance(item, str):
                continue
            tag = item.strip()
            # Пустое и написанное одними разделителями («///») технологией не
            # считается: ключ у такого пустой, и своей строки в списке оно не
            # получает.
            key = skill_key(tag)
            if not key:
                continue
            if key in seen_in_row:
                continue
            seen_in_row.add(key)
            canon_by_key.setdefault(key, tag)
            counts[key] = counts.get(key, 0) + 1

    items = []
    for key, cnt in counts.items():
        if cnt < min_count:
            continue
        items.append({
            "label": canon_by_key[key],
            "count": cnt,
            "mine": key in profile_set,
        })
    items.sort(key=lambda it: (-it["count"], it["label"].casefold()))
    return {
        "period": period,
        "min_count": min_count,
        "skills": items[:limit],
    }


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


def _weekdays_and_waits(
    applied_map: dict[int, datetime], first_resp_by_vid: dict[int, datetime]
) -> tuple[list[int], list[float]]:
    """Ответы по дням недели (Пн=0 … Вс=6) и сроки ожидания в секундах."""
    by_weekday = [0, 0, 0, 0, 0, 0, 0]
    waits: list[float] = []
    for vid, applied_at in applied_map.items():
        resp_ts = first_resp_by_vid.get(vid)
        if resp_ts is None:
            continue
        by_weekday[resp_ts.weekday()] += 1
        delta = (resp_ts - applied_at).total_seconds()
        if delta > 0:
            waits.append(delta)
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
    if not applied_map:
        return {
            "period": period,
            "by_weekday": [0, 0, 0, 0, 0, 0, 0],
            "median_seconds": None,
            "no_response_pct": None,
            "applied_count": 0,
            "responded_count": 0,
        }
    first_resp_by_vid = await _first_response_at(session, applied_map)
    by_weekday, waits = _weekdays_and_waits(applied_map, first_resp_by_vid)
    median_seconds = _median(waits)
    applied_count = len(applied_map)
    responded_count = len(first_resp_by_vid)
    no_response_pct = (
        round((applied_count - responded_count) / applied_count * 100)
        if applied_count > 0 else None
    )
    return {
        "period": period,
        "by_weekday": by_weekday,
        "median_seconds": median_seconds,
        "no_response_pct": no_response_pct,
        "applied_count": applied_count,
        "responded_count": responded_count,
    }
