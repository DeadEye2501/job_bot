"""Отбор вакансий для списка на экране."""

from datetime import datetime

from sqlalchemy import String, case, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.models import (
    Company,
    HR,
    TelegramChannel,
    Vacancy,
    VacancyEvent,
    VacancyStatus,
    VacancyStatusHistory,
)

# Status codes from the UI map to VacancyStatus enum members. The codes are
# the same kebab-case identifiers used in CSS classes / JS state.
_STATUS_BY_CODE = {
    "new": VacancyStatus.NEW,
    "applied": VacancyStatus.APPLIED,
    "answered": VacancyStatus.ANSWERED,
    "test": VacancyStatus.TEST,
    "invitation": VacancyStatus.INVITATION,
    "in-progress": VacancyStatus.IN_PROGRESS,
    "offer": VacancyStatus.OFFER,
    "decline": VacancyStatus.DECLINE,
    "ghosting": VacancyStatus.GHOSTING,
    "scam": VacancyStatus.SCAM,
    "not-fit": VacancyStatus.NOT_FIT,
}


VACANCY_SORTS = {
    "newest",
    "oldest",
    "score_desc",
    "score_asc",
    "status_active_first",
    "status_new_first",
}


# Mirrors STATUS_PRIORITY_ACTIVE_FIRST / NEW_FIRST in client/web/main.html.
# Statuses outside the explicit list fall to the tail (priority 999).
_STATUS_PRIORITY_ACTIVE_FIRST = {
    VacancyStatus.OFFER: 0,
    VacancyStatus.TEST: 1,
    VacancyStatus.INVITATION: 2,
    VacancyStatus.IN_PROGRESS: 3,
    VacancyStatus.ANSWERED: 4,
    VacancyStatus.APPLIED: 5,
    VacancyStatus.NEW: 6,
    VacancyStatus.NOT_FIT: 7,
    VacancyStatus.SCAM: 8,
    VacancyStatus.DECLINE: 9,
    VacancyStatus.GHOSTING: 10,
}


_STATUS_PRIORITY_NEW_FIRST = {
    VacancyStatus.NEW: 0,
    VacancyStatus.APPLIED: 1,
    VacancyStatus.ANSWERED: 2,
    VacancyStatus.TEST: 3,
    VacancyStatus.INVITATION: 4,
    VacancyStatus.IN_PROGRESS: 5,
    VacancyStatus.OFFER: 6,
    VacancyStatus.NOT_FIT: 7,
    VacancyStatus.SCAM: 8,
    VacancyStatus.DECLINE: 9,
    VacancyStatus.GHOSTING: 10,
}


def _greatest_pair(a, b):
    # NULL-safe row-wise greatest: SQLite has no GREATEST(), and
    # NULL > anything is NULL, so we have to spell it out.
    return case((a.is_(None), b), (b.is_(None), a), (a > b, a), else_=b)


def _greatest(*cols):
    out = cols[0]
    for c in cols[1:]:
        out = _greatest_pair(out, c)
    return out


async def list_vacancies(
    session: AsyncSession,
    sort: str = "newest",
    search: str | None = None,
    statuses: list[str] | None = None,
    channels: list[str] | None = None,
    companies: list[str] | None = None,
    score_min: int | None = None,
    score_max: int | None = None,
    salary_min: float | None = None,
    salary_max: float | None = None,
    grade: str | None = None,
    remote: str | None = None,
    hr_contact: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> list[Vacancy]:
    """Vacancies ordered per ``sort`` key, HR / company / channel eager-loaded.

    Activity timestamp (used by newest/oldest and as the tiebreaker for the
    other sorts) is the per-row max of ``vacancy.created_at``,
    ``vacancy.posted_at``, latest ``vacancy_event.created_at`` and latest
    ``vacancy_status_history.changed_at`` — same shape as
    :func:`list_vacancy_last_activity`, computed inline so SQL can sort on it.

    Filters (all optional, AND-combined):

    - ``search`` — case-insensitive substring match on title / description /
      company_name / linked company.name / notes / salary / grade / HR name /
      HR telegram username, plus the raw JSON of ``vacancy.stack``.
    - ``statuses`` — list of status codes (kebab-case, e.g. ``"in-progress"``);
      unknown codes are dropped silently.
    - ``channels`` — list of channel usernames (case-insensitive). Vacancies
      with no linked channel never match.
    - ``companies`` — list of company names (case-insensitive). Matches both
      linked ``company.name`` and the raw ``vacancy.company_name`` so unbinded
      vacancies still show up.
    - ``score_min`` / ``score_max`` — integer range; NULL scores never match.
    - ``salary_min`` / ``salary_max`` — window that has to overlap the
      vacancy's own ``salary_min``/``salary_max`` pair; both ends are
      inclusive. Rows whose salary held no number never match, whatever the
      window. Currency is not consulted: the numbers are compared as written.
    - ``grade`` / ``remote`` — substring match on the respective columns.
    - ``hr_contact`` — ``"with"`` / ``"without"`` filters by ``hr_id``
      presence; anything else (incl. ``None`` / ``"all"``) is a no-op.

    Excludes orphan rows (``is_parsed = False``) — those exist only because
    the parsing pipeline was interrupted between the row insert and the
    parse commit, and the UI shouldn't show them. They're picked up by
    ``IngestionPipeline.recover_orphan_vacancies`` on the next startup
    and either re-parsed or deleted as trash.
    """
    if sort not in VACANCY_SORTS:
        sort = "newest"

    event_agg = (
        select(
            VacancyEvent.vacancy_id.label("vid"),
            func.max(VacancyEvent.created_at).label("max_at"),
        )
        .group_by(VacancyEvent.vacancy_id)
        .subquery("event_agg")
    )
    status_agg = (
        select(
            VacancyStatusHistory.vacancy_id.label("vid"),
            func.max(VacancyStatusHistory.changed_at).label("max_at"),
        )
        .group_by(VacancyStatusHistory.vacancy_id)
        .subquery("status_agg")
    )

    activity_ts = _greatest(
        Vacancy.created_at,
        Vacancy.posted_at,
        event_agg.c.max_at,
        status_agg.c.max_at,
    )

    if sort == "oldest":
        order_by = (activity_ts.asc().nulls_last(), Vacancy.id.asc())
    elif sort == "score_desc":
        order_by = (Vacancy.score.desc().nulls_last(), activity_ts.desc(), Vacancy.id.desc())
    elif sort == "score_asc":
        order_by = (Vacancy.score.asc().nulls_last(), activity_ts.desc(), Vacancy.id.desc())
    elif sort == "status_active_first":
        priority = case(
            *[(Vacancy.status == s, p) for s, p in _STATUS_PRIORITY_ACTIVE_FIRST.items()],
            else_=999,
        )
        order_by = (priority.asc(), activity_ts.desc(), Vacancy.id.desc())
    elif sort == "status_new_first":
        priority = case(
            *[(Vacancy.status == s, p) for s, p in _STATUS_PRIORITY_NEW_FIRST.items()],
            else_=999,
        )
        order_by = (priority.asc(), activity_ts.desc(), Vacancy.id.desc())
    else:  # newest
        order_by = (activity_ts.desc().nulls_last(), Vacancy.id.desc())

    where_clauses = [Vacancy.is_parsed.is_(True)]
    needs_hr_join = False
    needs_company_join = False
    needs_channel_join = False

    if search and search.strip():
        q = f"%{search.strip().lower()}%"
        where_clauses.append(
            or_(
                func.lower(Vacancy.title).like(q),
                func.lower(Vacancy.description).like(q),
                func.lower(Vacancy.company_name).like(q),
                func.lower(Vacancy.notes).like(q),
                func.lower(Vacancy.salary).like(q),
                func.lower(Vacancy.grade).like(q),
                func.lower(HR.name).like(q),
                func.lower(HR.telegram_username).like(q),
                func.lower(Company.name).like(q),
                func.lower(cast(Vacancy.stack, String)).like(q),
            )
        )
        needs_hr_join = True
        needs_company_join = True

    if statuses:
        enum_values = [_STATUS_BY_CODE[s] for s in statuses if s in _STATUS_BY_CODE]
        if enum_values:
            where_clauses.append(Vacancy.status.in_(enum_values))

    # Регистр здесь сводится потому, что его сводит и выпадающий список
    # (см. :func:`list_vacancy_filter_options`): из «Контур» и «контур» он
    # оставляет первое встреченное написание, второго не предлагает вовсе, и
    # точное сравнение оставило бы вакансию со вторым написанием недостижимой
    # через фильтр. `lower` здесь свой, зарегистрированный в `adapters/db.py`,
    # и кириллицу он понимает.

    if channels:
        cleaned = [c.lower() for c in channels if c]
        if cleaned:
            where_clauses.append(func.lower(TelegramChannel.username).in_(cleaned))
            needs_channel_join = True

    if companies:
        cleaned = [c.lower() for c in companies if c]
        if cleaned:
            where_clauses.append(
                or_(
                    func.lower(Company.name).in_(cleaned),
                    func.lower(Vacancy.company_name).in_(cleaned),
                )
            )
            needs_company_join = True

    if score_min is not None:
        where_clauses.append(Vacancy.score >= score_min)
    if score_max is not None:
        where_clauses.append(Vacancy.score <= score_max)

    # Окно и вилка вакансии сравниваются на пересечение, поэтому границы
    # сходятся крест-накрест. У вакансии без чисел обе колонки пусты, и
    # сравнение с пустотой отсеивает её само.
    if salary_min is not None:
        where_clauses.append(Vacancy.salary_max >= salary_min)
    if salary_max is not None:
        where_clauses.append(Vacancy.salary_min <= salary_max)

    if grade:
        where_clauses.append(func.lower(Vacancy.grade).like(f"%{grade.lower()}%"))

    if remote:
        where_clauses.append(func.lower(Vacancy.remote).like(f"%{remote.lower()}%"))

    if hr_contact == "with":
        where_clauses.append(Vacancy.hr_id.is_not(None))
    elif hr_contact == "without":
        where_clauses.append(Vacancy.hr_id.is_(None))

    if date_from is not None:
        where_clauses.append(activity_ts >= date_from)
    if date_to is not None:
        where_clauses.append(activity_ts <= date_to)

    stmt = (
        select(Vacancy)
        .outerjoin(event_agg, event_agg.c.vid == Vacancy.id)
        .outerjoin(status_agg, status_agg.c.vid == Vacancy.id)
    )
    if needs_hr_join:
        stmt = stmt.outerjoin(HR, HR.id == Vacancy.hr_id)
    if needs_company_join:
        stmt = stmt.outerjoin(Company, Company.id == Vacancy.company_id)
    if needs_channel_join:
        stmt = stmt.outerjoin(
            TelegramChannel, TelegramChannel.id == Vacancy.source_channel_id
        )

    final_stmt = (
        stmt
        .where(*where_clauses)
        .options(
            selectinload(Vacancy.hr),
            selectinload(Vacancy.company),
            selectinload(Vacancy.channel),
        )
        .order_by(*order_by)
    )
    if limit is not None:
        final_stmt = final_stmt.limit(limit).offset(offset)

    rows = await session.scalars(final_stmt)
    return list(rows.all())


async def list_vacancy_filter_options(
    session: AsyncSession,
) -> dict[str, list[str]]:
    """Distinct channel usernames + company names available as filter options.

    Returns the full set of channels / companies that appear on at least one
    parsed vacancy, irrespective of the currently-active filters. Companies
    cover both linked ``Company.name`` and the raw ``Vacancy.company_name``
    so that unbound vacancies still contribute their company to the picker.
    Names are deduplicated case-insensitively (the first-seen casing wins),
    then sorted by ``ru`` collation client-side.
    """
    channel_rows = await session.execute(
        select(TelegramChannel.username)
        .join(Vacancy, Vacancy.source_channel_id == TelegramChannel.id)
        .where(
            Vacancy.is_parsed.is_(True),
            TelegramChannel.username.is_not(None),
        )
        .distinct()
    )
    channels: list[str] = []
    seen_ch: set[str] = set()
    for (name,) in channel_rows.all():
        if not name:
            continue
        key = name.lower()
        if key in seen_ch:
            continue
        seen_ch.add(key)
        channels.append(name)

    linked_rows = await session.execute(
        select(Company.name)
        .join(Vacancy, Vacancy.company_id == Company.id)
        .where(Vacancy.is_parsed.is_(True), Company.name.is_not(None))
        .distinct()
    )
    raw_rows = await session.execute(
        select(Vacancy.company_name)
        .where(
            Vacancy.is_parsed.is_(True),
            Vacancy.company_name.is_not(None),
        )
        .distinct()
    )
    companies: list[str] = []
    seen_co: set[str] = set()
    for source in (linked_rows.all(), raw_rows.all()):
        for (name,) in source:
            if not name:
                continue
            cleaned = name.strip()
            if not cleaned or cleaned == "—":
                continue
            key = cleaned.lower()
            if key in seen_co:
                continue
            seen_co.add(key)
            companies.append(cleaned)

    return {"channels": channels, "companies": companies}


async def list_vacancy_last_activity(
    session: AsyncSession, vacancy_ids: list[int]
) -> dict[int, datetime]:
    """Return latest activity timestamp per vacancy id.

    Activity is the max timestamp among:
    - vacancy.created_at / vacancy.posted_at
    - latest VacancyEvent.created_at
    - latest VacancyStatusHistory.changed_at
    """
    ids = [int(x) for x in vacancy_ids if x is not None]
    if not ids:
        return {}

    event_rows = (
        await session.execute(
            select(
                VacancyEvent.vacancy_id,
                func.max(VacancyEvent.created_at).label("max_event_at"),
            )
            .where(VacancyEvent.vacancy_id.in_(ids))
            .group_by(VacancyEvent.vacancy_id)
        )
    ).all()
    status_rows = (
        await session.execute(
            select(
                VacancyStatusHistory.vacancy_id,
                func.max(VacancyStatusHistory.changed_at).label("max_status_at"),
            )
            .where(VacancyStatusHistory.vacancy_id.in_(ids))
            .group_by(VacancyStatusHistory.vacancy_id)
        )
    ).all()

    event_by_id = {int(v_id): ts for v_id, ts in event_rows if v_id is not None and ts is not None}
    status_by_id = {int(v_id): ts for v_id, ts in status_rows if v_id is not None and ts is not None}

    out: dict[int, datetime] = {}
    base_rows = (
        await session.execute(
            select(Vacancy.id, Vacancy.posted_at, Vacancy.created_at).where(Vacancy.id.in_(ids))
        )
    ).all()
    for v_id, posted_at, created_at in base_rows:
        if v_id is None:
            continue
        candidates = [created_at, posted_at, event_by_id.get(int(v_id)), status_by_id.get(int(v_id))]
        vals = [x for x in candidates if x is not None]
        if vals:
            out[int(v_id)] = max(vals)
    return out
