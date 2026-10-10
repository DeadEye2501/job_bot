"""Числа карточки источника вакансий — канала или агрегатора."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.funnel import APPLIED, FIT_EXCLUDE, RESPONDED, percent_or_none
from backend.models import Vacancy
from backend.payloads import SourceStats
from backend.repository.vacancies_common import PARSED_ONLY, count_by_status

_RATE_WINDOW_DAYS = 30


async def _vacancies_per_day(session: AsyncSession, from_source) -> float:
    """Сколько разобранных вакансий в день источник приносит в последнем окне.

    Окно своё, а не «за всё время»: источник, замолчавший полгода назад,
    иначе выглядел бы таким же живым, как вчерашний.
    """
    since = datetime.now(timezone.utc) - timedelta(days=_RATE_WINDOW_DAYS)
    recent_count = int(
        (
            await session.execute(
                select(func.count(Vacancy.id))
                .where(from_source, Vacancy.created_at >= since, PARSED_ONLY)
            )
        ).scalar_one()
    )
    return round(recent_count / _RATE_WINDOW_DAYS, 1)


async def source_stats(session: AsyncSession, from_source) -> SourceStats:
    """Числа карточки источника: разбивка по статусам, темп и три доли.

    `from_source` — условие «вакансия пришла из этого источника»: каналы и
    агрегаторы считаются одинаково и различаются только колонкой ссылки.

    Доли считаются одна от другой, ступенями воронки: годные от всех,
    отклики от годных, ответы от откликов — каждая отвечает на свой вопрос
    об источнике, и общий знаменатель смазал бы все три. Считаются они за всё
    время, а темп — за окно: доли говорят, каков источник вообще, темп — жив
    ли он сейчас.
    """
    counts_by_enum = await count_by_status(session, from_source, PARSED_ONLY)
    per_day = await _vacancies_per_day(session, from_source)
    total = sum(counts_by_enum.values())
    fit_total = sum(
        n for s, n in counts_by_enum.items() if s not in FIT_EXCLUDE
    )
    applied_total = sum(
        n for s, n in counts_by_enum.items() if s in APPLIED
    )
    responded_total = sum(
        n for s, n in counts_by_enum.items() if s in RESPONDED
    )
    return SourceStats(
        status_counts={
            status.value: count for status, count in counts_by_enum.items()
        },
        total=total,
        vacancies_per_day=per_day,
        fit_percent=percent_or_none(fit_total, total),
        apply_percent=percent_or_none(applied_total, fit_total),
        response_percent=percent_or_none(responded_total, applied_total),
    )
