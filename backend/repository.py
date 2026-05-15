import logging
import re
from datetime import date, datetime, timedelta, timezone
from difflib import SequenceMatcher
from typing import Any

from sqlalchemy import String, and_, case, cast, delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.cv_parser import ParsedCv
from backend.models import (
    HR,
    AppSetting,
    Blacklist,
    Company,
    Message,
    Profile,
    ProfileExperience,
    ProfileLanguage,
    ProfileSkill,
    StatusHistorySource,
    TelegramChannel,
    TrashEvent,
    Vacancy,
    VacancyEvent,
    VacancyStatus,
    VacancyStatusHistory,
    profile_experience_skills,
)
from backend.domain import should_apply_status
from backend.payloads import (
    Classification,
    ChannelDetail,
    ChannelStats,
    ChannelWithCount,
    CompanyDetail,
    CompanyWithCount,
    HrDetail,
    HrWithCount,
    VacancyDetail,
)


logger = logging.getLogger(__name__)


# Зеркало JS-`_ensureTrailingPeriod` (client/web/main.html). Применяется
# ко всем записям `vacancy_status_history.explanation`, чтобы заметки в
# таймлайне рендерились единообразно как "Status: reason." — независимо
# от того, ЛЛМ ли это, ручной ввод или подпись авто-отправки.
def _ensure_trailing_period(s: str | None) -> str | None:
    if s is None:
        return None
    trimmed = s.strip()
    if not trimmed:
        return None
    if trimmed[-1] in ".!?…:":
        return trimmed
    return trimmed + "."


async def find_known_hr(
    session: AsyncSession,
    telegram_user_id: int,
    telegram_username: str | None = None,
) -> HR | None:
    """Look up an HR by telegram user_id, fall back to @username.

    The fallback handles HRs created from the Contacts/HR pane via username
    only — when their first incoming DM arrives we now know their user_id
    via the Pyrogram payload, but the row still has user_id NULL. Caller
    is responsible for backfilling ``hr.telegram_user_id`` after a username
    match so subsequent lookups hit the fast path.
    """
    hr = (
        await session.scalars(
            select(HR).where(HR.telegram_user_id == telegram_user_id)
        )
    ).first()
    if hr is not None:
        return hr
    if telegram_username:
        hr = (
            await session.scalars(
                select(HR).where(HR.telegram_username == telegram_username)
            )
        ).first()
    return hr


async def list_hrs_for_backfill(
    session: AsyncSession,
) -> list[tuple[HR, int]]:
    """Every HR with a Telegram identifier + the highest incoming
    ``tg_message_id`` we already have (0 if none). Used by Bot startup to
    pull whatever we missed while the bot was off — broader than
    ``list_open_hr_chats``, which only covers HRs we ever messaged first.
    """
    hrs = list(
        (
            await session.scalars(
                select(HR).where(
                    (HR.telegram_user_id.is_not(None))
                    | (HR.telegram_username.is_not(None))
                )
            )
        ).all()
    )
    result: list[tuple[HR, int]] = []
    for hr in hrs:
        last_seen = (
            await session.scalars(
                select(func.max(Message.tg_message_id)).where(
                    Message.hr_id == hr.id, Message.is_incoming
                )
            )
        ).first()
        result.append((hr, last_seen or 0))
    return result


async def list_open_hr_chats(
    session: AsyncSession,
) -> list[tuple[HR, int]]:
    hrs = list(
        (
            await session.scalars(
                select(HR)
                .where(HR.telegram_user_id.is_not(None))
                .where(
                    select(Message.id)
                    .where(Message.hr_id == HR.id, ~Message.is_incoming)
                    .exists()
                )
            )
        ).all()
    )
    result: list[tuple[HR, int]] = []
    for hr in hrs:
        last_seen = (
            await session.scalars(
                select(func.max(Message.tg_message_id)).where(
                    Message.hr_id == hr.id, Message.is_incoming
                )
            )
        ).first()
        result.append((hr, last_seen or 0))
    return result


async def find_latest_vacancy_id_for_hr(
    session: AsyncSession,
    hr_id: int,
    *,
    as_of: datetime | None = None,
) -> int | None:
    """Самая свежая вакансия, привязанная к HR — по posted_at (с fallback на
    created_at, когда posted_at null'нут). Используется для атрибуции HR-
    ответов: если HR пишет нам, считаем что он реагирует на самую свежую
    из его вакансий, независимо от того, отправляли ли мы ему отклик через
    бот (юзер мог написать с телефона/из десктопа).

    ``as_of`` — таймстемп сообщения HR'а. Вакансии, появившиеся ПОЗЖЕ него,
    отбрасываются: иначе старое сообщение из catch-up может «откатить
    статус» только-что добавленной вакансии (time-travel). Также берутся
    только полностью распаршенные вакансии (``is_parsed=True``), чтобы
    DM в parse-window не флипнул статус ещё не готовой строки.

    Clock-skew nuance: ``as_of`` приходит от Telegram (msg.date), а
    ``Vacancy.created_at`` пишется локальным ``func.now()``. Если часы
    клиента опаздывают относительно Telegram-серверного времени, существует
    тонкий race с auto-send'ом, который committs и сразу шлёт DM — но в
    single-user setup (Pyrogram-сессия привязана к ОС-времени) клиентское
    время и Telegram-серверное обычно синкаются NTP-сервисом, окно
    рассогласования = единицы секунд. Документировано вместо переключения
    ``created_at`` на ``msg.date`` исходного поста (которое потребовало
    бы тащить msg-time через 5 слоёв ingestion'а).
    """
    stmt = (
        select(Vacancy)
        .where(Vacancy.hr_id == hr_id, Vacancy.is_parsed.is_(True))
        .order_by(
            func.coalesce(Vacancy.posted_at, Vacancy.created_at).desc(),
            Vacancy.id.desc(),
        )
        .limit(1)
    )
    if as_of is not None:
        stmt = stmt.where(
            func.coalesce(Vacancy.posted_at, Vacancy.created_at) <= as_of
        )
    latest = (await session.scalars(stmt)).first()
    return latest.id if latest else None


async def count_recent_outgoing_with_vacancy_for_hr(
    session: AsyncSession,
    hr_id: int,
    *,
    window_days: int = 14,
) -> int:
    """Сколько cover-letter'ов мы отправили этому HR'у за последние
    ``window_days`` дней. Считаются только outgoing rows с привязанным
    ``vacancy_id`` — ручные сообщения из чата Contacts (без vacancy_id)
    игнорируются. Подписан на 0 при отсутствии истории.

    Используется в auto / manual send-ветке для решения «полный cover
    letter + CV (count==0) vs short follow-up без вложений (count>=1)».
    Cutoff считаем в Python, чтобы не зависеть от диалекта date-arithmetic.

    SEND_LOCKED dev-режим Message-rows не пишет → в dev-сценариях count
    всегда 0, что и нужно: dev тестирует full-cover-letter путь.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    stmt = select(func.count(Message.id)).where(
        Message.hr_id == hr_id,
        ~Message.is_incoming,
        Message.vacancy_id.is_not(None),
        Message.sent_at >= cutoff,
    )
    return (await session.scalar(stmt)) or 0


async def resolve_reply_target_vacancy(
    session: AsyncSession,
    hr_id: int,
    reply_to_tg_msg_id: int,
) -> int | None:
    """Найти vacancy_id нашего outgoing-сообщения, на которое HR ответил
    через Telegram-reply (`reply_to_message_id`). Возвращает ``None``
    если процитированное сообщение не наше / не найдено / без vacancy_id
    (ручная переписка из Contacts).

    Уникальность гарантирует UniqueConstraint
    ``(hr_id, tg_message_id, is_incoming)`` — outgoing-row с заданным
    tg_message_id для HR'а ровно одна.
    """
    stmt = (
        select(Message.vacancy_id)
        .where(
            Message.hr_id == hr_id,
            ~Message.is_incoming,
            Message.tg_message_id == reply_to_tg_msg_id,
        )
        .limit(1)
    )
    return await session.scalar(stmt)


def refresh_hr_username(hr: HR, sender_username: str | None) -> None:
    if sender_username and hr.telegram_username != sender_username:
        hr.telegram_username = sender_username


async def save_incoming_message(
    session: AsyncSession,
    hr_id: int,
    vacancy_id: int | None,
    text: str,
    tg_message_id: int,
    received_at: datetime,
    *,
    media_kind: str | None = None,
    media_path: str | None = None,
    media_name: str | None = None,
) -> Message:
    new_msg = Message(
        is_incoming=True,
        hr_id=hr_id,
        vacancy_id=vacancy_id,
        text=text,
        tg_message_id=tg_message_id,
        sent_at=received_at,
        media_kind=media_kind,
        media_path=media_path,
        media_name=media_name,
    )
    session.add(new_msg)
    await session.flush()
    return new_msg


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


_SALARY_TOKEN_RE = re.compile(r"\d+(?:[.,]\d+)?\s*[kк]?", re.IGNORECASE)


def _parse_usd_range(salary: str | None) -> tuple[float, float] | None:
    """Port of the original JS parseUsdRange used by the salary filter.

    Returns ``(min, max)`` in absolute USD when the string mentions ``$``
    or ``usd``; otherwise ``None`` (those vacancies are intentionally
    excluded from a salary-range filter — same behaviour as the JS).
    Numbers with ``K`` / ``к`` suffix are multiplied by 1000.
    """
    if not salary:
        return None
    s = salary.lower()
    if s == "—" or ("$" not in s and "usd" not in s):
        return None
    values: list[float] = []
    for tok in _SALARY_TOKEN_RE.findall(s):
        has_k = "k" in tok.lower() or "к" in tok.lower()
        cleaned = re.sub(r"[^\d.,]", "", tok).replace(",", ".")
        try:
            num = float(cleaned)
        except ValueError:
            continue
        values.append(num * 1000 if has_k else num)
    if not values:
        return None
    return min(values), max(values)


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

    # NB: the channels/companies filters compare exactly (no LOWER) on
    # purpose. SQLite's built-in LOWER() is ASCII-only, so a Russian name
    # like "Яндекс" stays "Яндекс" SQL-side while Python lowers it to
    # "яндекс" — the IN comparison silently misses every cyrillic row.
    # Since the dropdown values are sourced from these very columns
    # (see :func:`list_vacancy_filter_options`), exact match works
    # case-correctly and avoids the UDF detour.

    if channels:
        cleaned = [c for c in channels if c]
        if cleaned:
            where_clauses.append(TelegramChannel.username.in_(cleaned))
            needs_channel_join = True

    if companies:
        cleaned = [c for c in companies if c]
        if cleaned:
            where_clauses.append(
                or_(
                    Company.name.in_(cleaned),
                    Vacancy.company_name.in_(cleaned),
                )
            )
            needs_company_join = True

    if score_min is not None:
        where_clauses.append(Vacancy.score >= score_min)
    if score_max is not None:
        where_clauses.append(Vacancy.score <= score_max)

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

    has_salary_filter = (salary_min is not None or salary_max is not None)

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
    # SQL-level pagination is skipped when the salary filter is active —
    # salary is a Python post-fetch filter (USD-string regex parse) and a
    # mid-cut LIMIT would silently chop rows that haven't been salary-tested
    # yet, leaving subsequent offsets pointing past phantom rows. The bridge
    # signals this to the UI by reporting has_more=False so the user sees
    # the complete (filtered) list as a single page.
    if limit is not None and not has_salary_filter:
        final_stmt = final_stmt.limit(limit).offset(offset)

    rows = await session.scalars(final_stmt)
    results = list(rows.all())

    if has_salary_filter:
        def _matches(v: Vacancy) -> bool:
            r = _parse_usd_range(v.salary)
            if r is None:
                return False
            lo, hi = r
            if salary_min is not None and hi < salary_min:
                return False
            if salary_max is not None and lo > salary_max:
                return False
            return True
        results = [v for v in results if _matches(v)]

    return results


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


async def get_vacancy_detail(
    session: AsyncSession, vacancy_id: int
) -> VacancyDetail | None:
    """Vacancy + status history + pipeline events, all sorted newest-first.

    Returns ``None`` if the vacancy doesn't exist. History and events are
    queried separately because there are no ORM relationships pointing
    Vacancy -> these tables (and adding them would silently double the
    write-side ON DELETE behaviour).
    """
    vacancy = (
        await session.scalars(
            select(Vacancy)
            .where(Vacancy.id == vacancy_id)
            .options(
                selectinload(Vacancy.hr),
                selectinload(Vacancy.company),
                selectinload(Vacancy.channel),
            )
        )
    ).first()
    if vacancy is None:
        return None

    history = list(
        (
            await session.scalars(
                select(VacancyStatusHistory)
                .where(VacancyStatusHistory.vacancy_id == vacancy_id)
                .order_by(
                    VacancyStatusHistory.changed_at.desc(),
                    VacancyStatusHistory.id.desc(),
                )
            )
        ).all()
    )
    events = list(
        (
            await session.scalars(
                select(VacancyEvent)
                .where(VacancyEvent.vacancy_id == vacancy_id)
                .order_by(
                    VacancyEvent.created_at.desc(),
                    VacancyEvent.id.desc(),
                )
            )
        ).all()
    )
    return VacancyDetail(vacancy=vacancy, history=history, events=events)


async def change_vacancy_status(
    session: AsyncSession,
    vacancy_id: int,
    new_status: VacancyStatus,
    explanation: str | None,
) -> VacancyStatusHistory | None:
    """Manual status change from the UI.

    Overrides stickiness unconditionally — every UI call is by definition
    explicit, so sticky statuses (Offer, Decline, Not Fit…) move on user
    request. Use ``apply_classification`` for the auto-classifier path
    that *should* respect stickiness.

    The ``applied`` flag in the history row reflects whether this row
    actually mutated ``vacancy.status``: same status + non-empty
    explanation = comment-only, ``applied=False``.

    No-op short-circuit: if the status is unchanged AND the explanation
    is empty/whitespace, no row is written and ``None`` is returned —
    avoids history pollution from accidental "Применить" clicks. Returns
    ``None`` also if the vacancy doesn't exist.

    Caller wraps in ``session.begin()``.
    """
    vacancy = await session.get(Vacancy, vacancy_id)
    if vacancy is None:
        return None
    previous = vacancy.status
    cleaned_explanation = _ensure_trailing_period(explanation)
    status_changed = previous != new_status
    if not status_changed and cleaned_explanation is None:
        return None
    if status_changed:
        vacancy.status = new_status
    history = VacancyStatusHistory(
        vacancy_id=vacancy_id,
        message_id=None,
        previous_status=previous,
        status=new_status,
        explanation=cleaned_explanation,
        applied=status_changed,
        source=StatusHistorySource.USER,
    )
    session.add(history)
    await session.flush()
    if status_changed:
        logger.info(
            "vacancy %d: status %s -> %s (manual, applied=%s)",
            vacancy_id,
            previous.value if previous else None,
            new_status.value,
            status_changed,
        )
    else:
        logger.debug(
            "vacancy %d: comment-only history added (status=%s)",
            vacancy_id,
            new_status.value,
        )
    return history


async def update_status_history_explanation(
    session: AsyncSession, history_id: int, explanation: str | None
) -> bool:
    """Replace ``vacancy_status_history.explanation`` для одной записи.

    Зеркалит поведение ``update_vacancy_notes``: empty / whitespace-only
    нормализуется в ``NULL`` (UI рендерит «без комментария» для NULL,
    отличая «удалили коммент» от «забыли набрать»). Returns False если
    history-id не найден. Caller wraps in ``session.begin()``.
    """
    row = await session.get(VacancyStatusHistory, history_id)
    if row is None:
        return False
    row.explanation = _ensure_trailing_period(explanation)
    return True


async def update_vacancy_notes(
    session: AsyncSession, vacancy_id: int, notes: str | None
) -> bool:
    """Replace ``vacancy.notes``. Returns False if the vacancy is missing.

    Empty / whitespace-only ``notes`` is normalized to ``NULL`` so a textarea
    with only spaces or newlines doesn't leave behind a "ghost" non-empty
    value that the UI can't tell apart from real notes. Leading / trailing
    whitespace inside otherwise non-empty notes is preserved verbatim so the
    JS-side baseline (``notesLastSaved``) matches the textarea content
    character-for-character on the next debounce — otherwise we'd be re-saving
    the same trimmed string on every keystroke.
    """
    vacancy = await session.get(Vacancy, vacancy_id)
    if vacancy is None:
        return False
    normalized: str | None
    if notes is None or not notes.strip():
        normalized = None
    else:
        normalized = notes
    vacancy.notes = normalized
    await session.flush()
    return True


async def set_vacancy_hr(
    session: AsyncSession, vacancy_id: int, hr_id: int | None
) -> bool:
    """Link or unlink the HR for a vacancy. Returns False if vacancy missing."""
    vacancy = await session.get(Vacancy, vacancy_id)
    if vacancy is None:
        return False
    previous_hr_id = vacancy.hr_id
    target_hr: HR | None = None
    if hr_id is not None:
        target_hr = await session.get(HR, hr_id)
        if target_hr is None:
            raise ValueError(f"set_vacancy_hr: HR {hr_id} does not exist")
    if previous_hr_id == hr_id:
        # No effective change -> no timeline noise.
        return True
    previous_name: str | None = None
    if previous_hr_id is not None:
        prev_hr = await session.get(HR, previous_hr_id)
        if prev_hr is not None:
            previous_name = prev_hr.name or prev_hr.telegram_username
    next_name: str | None = None
    if target_hr is not None:
        next_name = target_hr.name or target_hr.telegram_username
    vacancy.hr_id = hr_id
    await add_vacancy_event(
        session,
        vacancy_id,
        kind="linked_hr",
        payload={
            "previous_id": previous_hr_id,
            "previous_name": previous_name,
            "new_id": hr_id,
            "new_name": next_name,
        },
    )
    await session.flush()
    logger.info(
        "vacancy %d: hr_id %s -> %s",
        vacancy_id,
        previous_hr_id,
        hr_id,
    )
    return True


async def set_vacancy_company(
    session: AsyncSession, vacancy_id: int, company_id: int | None
) -> bool:
    """Link or unlink the company for a vacancy. False if vacancy missing."""
    vacancy = await session.get(Vacancy, vacancy_id)
    if vacancy is None:
        return False
    previous_company_id = vacancy.company_id
    target_company: Company | None = None
    if company_id is not None:
        target_company = await session.get(Company, company_id)
        if target_company is None:
            raise ValueError(
                f"set_vacancy_company: company {company_id} does not exist"
            )
    if previous_company_id == company_id:
        return True
    previous_name: str | None = None
    if previous_company_id is not None:
        prev_company = await session.get(Company, previous_company_id)
        if prev_company is not None:
            previous_name = prev_company.name
    next_name: str | None = None
    if target_company is not None:
        next_name = target_company.name
    vacancy.company_id = company_id
    await add_vacancy_event(
        session,
        vacancy_id,
        kind="linked_company",
        payload={
            "previous_id": previous_company_id,
            "previous_name": previous_name,
            "new_id": company_id,
            "new_name": next_name,
        },
    )
    await session.flush()
    logger.info(
        "vacancy %d: company_id %s -> %s",
        vacancy_id,
        previous_company_id,
        company_id,
    )
    return True


async def create_hr(
    session: AsyncSession,
    *,
    name: str | None,
    telegram_username: str | None,
    telegram_user_id: int | None = None,
    notes: str | None = None,
) -> HR:
    """Insert a new HR row. Caller wraps in ``session.begin()``.

    No deduping by username — the UI's HR-picker already shows existing
    HRs and the user has to explicitly click "Создать нового HR". If they
    chose to create rather than link, we trust that.
    """
    hr = HR(
        name=(name or None),
        telegram_username=(telegram_username or None),
        telegram_user_id=telegram_user_id,
        notes=(notes or None),
    )
    session.add(hr)
    await session.flush()
    logger.info(
        "Created HR id=%d name=%r username=%s",
        hr.id,
        name,
        telegram_username,
    )
    return hr


async def create_company(
    session: AsyncSession,
    *,
    name: str,
    website: str | None = None,
    aliases: list[str] | None = None,
    notes: str | None = None,
) -> Company:
    """Insert a new Company row. Raises if name is empty.

    Unique constraint on ``company.name`` will surface as IntegrityError if
    the user tries to create a duplicate; caller can convert that into a
    user-facing message.
    """
    normalized = (name or "").strip()
    if not normalized:
        raise ValueError("create_company: name is required")
    company = Company(
        name=normalized,
        aliases=list(aliases or []),
        website=(website or None),
        notes=(notes or None),
    )
    session.add(company)
    await session.flush()
    logger.info(
        "Created company id=%d name=%r website=%s",
        company.id,
        normalized,
        website,
    )
    return company


async def record_trash_event(
    session: AsyncSession,
    *,
    source_channel_id: int | None,
    source_msg_id: int | None,
    reason: str | None,
) -> None:
    """Записать факт «пост из канала классифицирован как trash».
    Используется ДО удаления Vacancy-ряда (в auto-ingest режиме), чтобы
    трекать «сколько мусора прислал канал» — иначе после delete этой
    информации в БД не остаётся. Caller оборачивает в session.begin().
    """
    session.add(TrashEvent(
        source_channel_id=source_channel_id,
        source_msg_id=source_msg_id,
        reason=reason,
    ))


async def delete_vacancy(session: AsyncSession, vacancy_id: int) -> bool:
    """Hard-delete a vacancy + its history + its events.

    ``message.vacancy_id`` is nullified rather than deleted so the chat
    history stays intact (the user might still want to see the conversation
    with the HR after the vacancy was wiped). Returns False if the vacancy
    doesn't exist.

    Caller wraps in ``session.begin()``.
    """
    vacancy = await session.get(Vacancy, vacancy_id)
    if vacancy is None:
        return False
    await session.execute(
        update(Message)
        .where(Message.vacancy_id == vacancy_id)
        .values(vacancy_id=None)
    )
    await session.execute(
        delete(VacancyStatusHistory).where(
            VacancyStatusHistory.vacancy_id == vacancy_id
        )
    )
    await session.execute(
        delete(VacancyEvent).where(VacancyEvent.vacancy_id == vacancy_id)
    )
    await session.delete(vacancy)
    await session.flush()
    logger.info(
        "Deleted vacancy %d (msgs detached, history+events purged)", vacancy_id
    )
    return True


_HR_FIELD_UNSET = object()


async def list_vacancies_for_hr(
    session: AsyncSession,
    hr_id: int,
) -> list[Vacancy]:
    """All parsed vacancies for an HR, newest-first. Powers the «список
    вакансий» mini-list in the Contacts/HR detail pane.

    Skips ``is_parsed=False`` rows so half-built (crash-recovered) vacancies
    don't surface in the chip — the same gate the main vacancies list uses.
    """
    rows = (
        await session.scalars(
            select(Vacancy)
            .where(Vacancy.hr_id == hr_id, Vacancy.is_parsed.is_(True))
            .order_by(Vacancy.created_at.desc(), Vacancy.id.desc())
        )
    ).all()
    return list(rows)


async def list_messages_for_hr(
    session: AsyncSession,
    hr_id: int,
    *,
    limit: int = 50,
    before_id: int | None = None,
    before_sent_at: datetime | None = None,
) -> tuple[list[Message], bool]:
    """A page of messages for an HR, oldest-first (chat-render order).

    Fetches the newest ``limit`` messages strictly older than the cursor
    ``(before_sent_at, before_id)`` (or the tail of the chat if both are
    None), ordered ``sent_at DESC, id DESC`` then reversed to oldest-first.
    Returns ``(messages, has_more)`` so the UI knows whether to keep
    offering "load older".

    Cursor пагинация по составной паре `(sent_at, id)` — НЕ по чистому
    `id`. Catch-up бэкаппит исторические DM-ы офлайн-периода после ингеста
    свежих realtime-сообщений: id у "более старого по времени" ряда может
    оказаться выше, чем у уже отображённого. Чистая пагинация по
    `id < before_id` тогда либо пропускает ряды, либо возвращает дубли.
    Composite-cursor устраняет это.
    """
    q = select(Message).where(Message.hr_id == hr_id)
    if before_sent_at is not None and before_id is not None:
        # SQL row-value: (sent_at, id) < (before_sent_at, before_id).
        # SQLite поддерживает row-value сравнения с 3.15+ — у нас новее,
        # но на всякий случай пишем эквивалентный OR-вариант, чтобы не
        # привязываться к конкретной реализации row-value.
        q = q.where(
            or_(
                Message.sent_at < before_sent_at,
                and_(
                    Message.sent_at == before_sent_at,
                    Message.id < before_id,
                ),
            )
        )
    elif before_id is not None:
        # Backwards-compat для старых клиентов, не присылающих
        # before_sent_at: оставляем прежнее поведение.
        q = q.where(Message.id < before_id)
    rows = (
        await session.scalars(
            q.order_by(Message.sent_at.desc(), Message.id.desc())
            .limit(limit + 1)
        )
    ).all()
    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]
    return list(reversed(rows)), has_more


async def update_hr_fields(
    session: AsyncSession,
    hr_id: int,
    *,
    name=_HR_FIELD_UNSET,
    telegram_username=_HR_FIELD_UNSET,
    notes=_HR_FIELD_UNSET,
) -> bool:
    """Update one or more HR columns. Caller wraps in ``session.begin()``.

    Sentinel ``_HR_FIELD_UNSET`` distinguishes "don't touch" from "set to
    NULL", so a single call can patch any subset of columns. Empty strings
    collapse to NULL — the schema treats absence and empty equivalently.
    """
    hr = await session.get(HR, hr_id)
    if hr is None:
        return False
    changed = []
    if name is not _HR_FIELD_UNSET:
        hr.name = (str(name).strip() or None) if name is not None else None
        changed.append("name")
    if telegram_username is not _HR_FIELD_UNSET:
        if telegram_username is None:
            hr.telegram_username = None
        else:
            cleaned = str(telegram_username).strip()
            if cleaned.startswith("@"):
                cleaned = cleaned[1:].strip()
            hr.telegram_username = cleaned or None
        changed.append("telegram_username")
    if notes is not _HR_FIELD_UNSET:
        hr.notes = (str(notes).strip() or None) if notes is not None else None
        changed.append("notes")
    await session.flush()
    if changed:
        logger.debug("Updated HR %d fields=%s", hr_id, changed)
    return True


async def get_hr_detail(
    session: AsyncSession, hr_id: int
) -> HrDetail | None:
    """Detail payload for the Contacts / HR pane (05).

    Returns the HR row + most-recent linked company (id + name, by
    ``vacancy.created_at desc``) + total vacancy count + count of unread
    incoming messages. Returns ``None`` if the HR row is gone.
    """
    hr = await session.get(HR, hr_id)
    if hr is None:
        return None

    vacancy_count = int(
        await session.scalar(
            select(func.count(Vacancy.id)).where(Vacancy.hr_id == hr_id)
        )
        or 0
    )

    last_co_row = (
        await session.execute(
            select(Company.id, Company.name)
            .join(Vacancy, Vacancy.company_id == Company.id)
            .where(Vacancy.hr_id == hr_id)
            .order_by(Vacancy.created_at.desc(), Vacancy.id.desc())
            .limit(1)
        )
    ).first()
    last_company_id = last_co_row[0] if last_co_row else None
    last_company_name = last_co_row[1] if last_co_row else None

    unread_count = int(
        await session.scalar(
            select(func.count(Message.id)).where(
                Message.hr_id == hr_id,
                Message.is_incoming,
                Message.read_at.is_(None),
                Message.is_deleted.is_(False),
            )
        )
        or 0
    )

    blacklist_value = await _hr_blacklist_value(session, hr)

    return HrDetail(
        hr=hr,
        vacancy_count=vacancy_count,
        last_company_id=last_company_id,
        last_company_name=last_company_name,
        unread_count=unread_count,
        blacklist_value=blacklist_value,
    )


def hr_blacklist_candidates(hr: HR) -> list[str]:
    """Possible blacklist `value` strings for this HR — same format the
    `contacts_add_hr_to_blacklist` slot writes. Both forms are checked so
    a row added under one identifier (username) still surfaces if the HR
    later only has the other (user_id), or vice versa.
    """
    out: list[str] = []
    if hr.telegram_username:
        out.append(f"@{hr.telegram_username}")
    if hr.telegram_user_id is not None:
        out.append(f"user_id:{hr.telegram_user_id}")
    return out


async def _hr_blacklist_value(session: AsyncSession, hr: HR) -> str | None:
    candidates = hr_blacklist_candidates(hr)
    if not candidates:
        return None
    # Deterministic when both forms exist (rare — re-add across schema
    # changes): smallest id wins so the head chip's `title` doesn't
    # flicker between rows on different page loads.
    row = (
        await session.scalars(
            select(Blacklist)
            .where(
                Blacklist.kind == "hr",
                Blacklist.value.in_(candidates),
                Blacklist.active.is_(True),
            )
            .order_by(Blacklist.id.asc())
            .limit(1)
        )
    ).first()
    return row.value if row else None


async def list_hr_with_counts(
    session: AsyncSession,
    search: str | None = None,
    *,
    limit: int | None = None,
    offset: int = 0,
    sort_by: str = "vacancy_count",
) -> list[HrWithCount]:
    """All HRs with their vacancy count and most recent linked company.

    Used by the "Связать с HR" picker AND the Contacts/HR pane (05).

    ``sort_by``:
    - ``"vacancy_count"`` (default, picker): vacancy count DESC, then name —
      keeps prolific HRs at the top, the natural order for a linker.
    - ``"last_activity"`` (Contacts/HR): max(message.sent_at) DESC NULLS LAST,
      then name — последние, с кем была переписка, наверху.

    ``last_company_name`` is the company of the HR's most recent vacancy;
    NULL if that vacancy isn't linked to any company, even if older
    vacancies were. "Most recent" wins on purpose — older context is
    misleading for a picker.

    ``search`` is filtered Python-side via ``str.casefold()`` because
    SQLite's built-in ``lower()`` only handles ASCII — pure-SQL
    LIKE matching would silently miss Cyrillic case variants.

    ``limit``/``offset`` slice the result *after* the search filter so the
    caller can implement infinite-scroll. ``None`` limit (default) returns
    everything — preserves the picker's existing behaviour.
    """
    if sort_by == "last_activity":
        # Пре-агрегируем последнюю переписку отдельным GROUP BY hr_id вместо
        # коррелированного scalar-subquery в ORDER BY: иначе SQLite заново
        # сканировал бы message-таблицу по разу на каждого HR при сортировке.
        # Здесь — один проход по message с использованием ix_message_hr_id,
        # дальше LEFT JOIN на HR.
        last_act_subq = (
            select(
                Message.hr_id.label("hr_id"),
                func.max(Message.sent_at).label("last_act"),
            )
            .where(Message.is_deleted.is_(False))
            .group_by(Message.hr_id)
            .subquery()
        )
        base = (
            select(HR, func.count(Vacancy.id).label("cnt"))
            .outerjoin(Vacancy, Vacancy.hr_id == HR.id)
            .outerjoin(last_act_subq, last_act_subq.c.hr_id == HR.id)
            .group_by(HR.id, last_act_subq.c.last_act)
            .order_by(
                last_act_subq.c.last_act.desc().nullslast(),
                HR.name.asc(),
            )
        )
    else:
        base = (
            select(HR, func.count(Vacancy.id).label("cnt"))
            .outerjoin(Vacancy, Vacancy.hr_id == HR.id)
            .group_by(HR.id)
            .order_by(func.count(Vacancy.id).desc(), HR.name.asc())
        )
    counts = (await session.execute(base)).all()

    if search:
        q = search.strip().casefold()
        if q:
            counts = [
                (hr, cnt) for hr, cnt in counts
                if q in (hr.name or "").casefold()
                or q in (hr.telegram_username or "").casefold()
            ]

    if limit is not None:
        counts = counts[offset : offset + limit]

    latest_subq = (
        select(
            Vacancy.hr_id.label("hr_id"),
            Vacancy.company_id.label("company_id"),
            func.row_number()
            .over(
                partition_by=Vacancy.hr_id,
                order_by=(
                    Vacancy.created_at.desc(),
                    Vacancy.id.desc(),
                ),
            )
            .label("rn"),
        )
        .where(Vacancy.hr_id.is_not(None))
        .subquery()
    )
    last_co_rows = (
        await session.execute(
            select(latest_subq.c.hr_id, Company.name)
            .join(Company, Company.id == latest_subq.c.company_id)
            .where(latest_subq.c.rn == 1)
        )
    ).all()
    last_co: dict[int, str] = {hr_id: name for hr_id, name in last_co_rows}

    # Per-HR unread incoming count for the lime badge in the list pane.
    # Single GROUP BY query — beats N+1 separate counts.
    unread_rows = (
        await session.execute(
            select(Message.hr_id, func.count(Message.id))
            .where(
                Message.hr_id.is_not(None),
                Message.is_incoming,
                Message.read_at.is_(None),
                Message.is_deleted.is_(False),
            )
            .group_by(Message.hr_id)
        )
    ).all()
    unread_by_hr: dict[int, int] = {hr_id: int(n) for hr_id, n in unread_rows}

    # Active hr-blacklist values, all in one query — `is_blacklisted` is a
    # set-membership check per HR.
    bl_values = set(
        (
            await session.scalars(
                select(Blacklist.value).where(
                    Blacklist.kind == "hr",
                    Blacklist.active.is_(True),
                )
            )
        ).all()
    )

    def _is_blacklisted(hr: HR) -> bool:
        return any(c in bl_values for c in hr_blacklist_candidates(hr))

    return [
        HrWithCount(
            hr=hr,
            vacancy_count=int(cnt or 0),
            last_company_name=last_co.get(hr.id),
            unread_count=unread_by_hr.get(hr.id, 0),
            is_blacklisted=_is_blacklisted(hr),
        )
        for hr, cnt in counts
    ]


async def list_companies_with_counts(
    session: AsyncSession,
    search: str | None = None,
    *,
    limit: int | None = None,
    offset: int = 0,
) -> list[CompanyWithCount]:
    """All companies with their vacancy count + blacklist status.

    ``search`` is matched against name, aliases, and website using
    Python-side ``str.casefold()`` (SQLite's ``lower()`` is ASCII-only).
    ``limit``/``offset`` slice the result *after* the search filter so the
    Contacts/Companies pane can implement infinite scroll.
    """
    base = (
        select(Company, func.count(Vacancy.id).label("cnt"))
        .outerjoin(Vacancy, Vacancy.company_id == Company.id)
        .group_by(Company.id)
        .order_by(func.count(Vacancy.id).desc(), Company.name.asc())
    )
    rows = (await session.execute(base)).all()

    if search:
        q = search.strip().casefold()
        if q:
            def matches(co: Company) -> bool:
                if q in co.name.casefold():
                    return True
                if co.website and q in co.website.casefold():
                    return True
                for alias in (co.aliases or []):
                    if isinstance(alias, str) and q in alias.casefold():
                        return True
                return False
            rows = [(c, cnt) for c, cnt in rows if matches(c)]

    if limit is not None:
        rows = rows[offset : offset + limit]

    bl_values = set(
        (
            await session.scalars(
                select(Blacklist.value).where(
                    Blacklist.kind == "company",
                    Blacklist.active.is_(True),
                )
            )
        ).all()
    )

    return [
        CompanyWithCount(
            company=c,
            vacancy_count=int(cnt or 0),
            is_blacklisted=any(v in bl_values for v in company_blacklist_candidates(c)),
        )
        for c, cnt in rows
    ]


def channel_blacklist_candidates(ch: TelegramChannel) -> list[str]:
    """Возможные blacklist `value` строки для канала. Используется для
    case-insensitive lookup'а — username может быть mixed-case или нет.
    Сейчас возвращаем только @username; формат и регистр совпадает с
    тем, что пишет ``contacts_add_channel_to_blacklist`` slot.
    """
    if not ch.username:
        return []
    return [f"@{ch.username}"]


def channel_blacklist_preferred_value(ch: TelegramChannel) -> str | None:
    if not ch.username:
        return None
    return f"@{ch.username}"


async def _channel_blacklist_value(
    session: AsyncSession, ch: TelegramChannel
) -> str | None:
    """Если канал сейчас активно в blacklist'е, возвращаем точный
    `value` строки (для UI-чипа в detail-pane). None — если не в нём.
    """
    candidates = channel_blacklist_candidates(ch)
    if not candidates:
        return None
    row = (
        await session.scalars(
            select(Blacklist)
            .where(
                Blacklist.kind == "channel",
                Blacklist.value.in_(candidates),
                Blacklist.active.is_(True),
            )
            .order_by(Blacklist.id.asc())
            .limit(1)
        )
    ).first()
    return row.value if row is not None else None


async def list_telegram_channels(
    session: AsyncSession,
    search: str | None = None,
) -> list[ChannelWithCount]:
    """All Telegram channels with their vacancy count.

    Ordered: by vacancy_count desc (prolific channels rank higher), then
    title. is_active НЕ участвует в сортировке — иначе blacklisted каналы
    (forced is_active=false) сваливались бы в самый низ списка, чего юзер
    не просил.

    ``search`` is matched against title and ``@username`` Python-side via
    ``str.casefold()`` — Cyrillic safety, same as HR/Company lists.

    No pagination: channel lists are tiny (tens, not thousands).
    """
    # ``coalesce(title, username)`` для сортировки совпадает с тем, как UI
    # выбирает заголовок ряда (title если есть, иначе @username) — иначе
    # NULL-title каналы в SQLite ASC всплывают наверх и порядок ломается.
    title_or_username = func.coalesce(TelegramChannel.title, TelegramChannel.username)
    base = (
        select(TelegramChannel, func.count(Vacancy.id).label("cnt"))
        .outerjoin(Vacancy, Vacancy.source_channel_id == TelegramChannel.id)
        .group_by(TelegramChannel.id)
        .order_by(
            func.count(Vacancy.id).desc(),
            title_or_username.asc(),
        )
    )
    rows = (await session.execute(base)).all()

    if search:
        q = search.strip().casefold()
        if q:
            rows = [
                (ch, cnt) for ch, cnt in rows
                if q in (ch.title or "").casefold()
                or q in (ch.username or "").casefold()
            ]

    bl_values = set(
        (
            await session.scalars(
                select(Blacklist.value).where(
                    Blacklist.kind == "channel",
                    Blacklist.active.is_(True),
                )
            )
        ).all()
    )

    def _is_blacklisted(ch: TelegramChannel) -> bool:
        return any(c in bl_values for c in channel_blacklist_candidates(ch))

    return [
        ChannelWithCount(
            channel=ch,
            vacancy_count=int(cnt or 0),
            is_blacklisted=_is_blacklisted(ch),
        )
        for ch, cnt in rows
    ]


_CHANNEL_RATE_WINDOW_DAYS = 30
# Voronka classification — derived once, reused by `get_channel_detail`:
# - `_FIT_EXCLUDE`: статусы, которые НЕ считаются подходящими — либо
#   валидатор отверг как Not Fit, либо это Scam (мы заведомо не будем
#   взаимодействовать с источником).
# - `_APPLIED`: что мы реально отправили, либо ответ уже пришёл / заглох.
#   New = подходит, но ещё не отправили.
# - `_RESPONDED`: получили ответ от работодателя (включая отказ — Decline
#   тоже ответ). Applied = ждём, Ghosting = тишина.
_FIT_EXCLUDE: frozenset[VacancyStatus] = frozenset({
    VacancyStatus.NOT_FIT, VacancyStatus.SCAM,
})
_APPLIED: frozenset[VacancyStatus] = frozenset({
    VacancyStatus.APPLIED,
    VacancyStatus.ANSWERED,
    VacancyStatus.TEST,
    VacancyStatus.INVITATION,
    VacancyStatus.IN_PROGRESS,
    VacancyStatus.OFFER,
    VacancyStatus.DECLINE,
    VacancyStatus.GHOSTING,
})
_RESPONDED: frozenset[VacancyStatus] = frozenset({
    VacancyStatus.ANSWERED,
    VacancyStatus.TEST,
    VacancyStatus.INVITATION,
    VacancyStatus.IN_PROGRESS,
    VacancyStatus.OFFER,
    VacancyStatus.DECLINE,
})


def _percent_or_none(numerator: int, denominator: int) -> int | None:
    if denominator <= 0:
        return None
    return int(round(numerator / denominator * 100))


async def get_channel_detail(
    session: AsyncSession, channel_id: int
) -> ChannelDetail | None:
    """Detail-pane payload: the channel itself + computed stats.

    Two queries: one for the channel row, one GROUP BY status to compute
    counts. Per-day rate is a separate windowed COUNT(*) over the last
    30 days. KPI ratios come from the lifetime status_counts.
    """
    ch = await session.get(TelegramChannel, channel_id)
    if ch is None:
        return None

    rows = (
        await session.execute(
            select(Vacancy.status, func.count(Vacancy.id))
            .where(Vacancy.source_channel_id == channel_id)
            .group_by(Vacancy.status)
        )
    ).all()

    counts_by_enum: dict[VacancyStatus, int] = {}
    for status_enum, cnt in rows:
        counts_by_enum[status_enum] = int(cnt or 0)

    total = sum(counts_by_enum.values())
    fit_total = sum(
        n for s, n in counts_by_enum.items() if s not in _FIT_EXCLUDE
    )
    applied_total = sum(
        n for s, n in counts_by_enum.items() if s in _APPLIED
    )
    responded_total = sum(
        n for s, n in counts_by_enum.items() if s in _RESPONDED
    )

    since = datetime.now(timezone.utc) - timedelta(days=_CHANNEL_RATE_WINDOW_DAYS)
    recent_count = int(
        (
            await session.execute(
                select(func.count(Vacancy.id))
                .where(
                    Vacancy.source_channel_id == channel_id,
                    Vacancy.created_at >= since,
                )
            )
        ).scalar_one()
    )
    vacancies_per_day = round(recent_count / _CHANNEL_RATE_WINDOW_DAYS, 1)

    status_counts = {
        status.value: counts_by_enum.get(status, 0) for status in VacancyStatus
    }

    blacklist_value = await _channel_blacklist_value(session, ch)

    return ChannelDetail(
        channel=ch,
        stats=ChannelStats(
            status_counts=status_counts,
            total=total,
            vacancies_per_day=vacancies_per_day,
            fit_percent=_percent_or_none(fit_total, total),
            apply_percent=_percent_or_none(applied_total, fit_total),
            response_percent=_percent_or_none(responded_total, applied_total),
        ),
        blacklist_value=blacklist_value,
    )


async def set_blacklist_active(
    session: AsyncSession, blacklist_id: int, active: bool
) -> bool:
    """Toggle Blacklist.active. Returns False if the row is missing.
    Caller wraps in ``session.begin()``.
    """
    row = await session.get(Blacklist, blacklist_id)
    if row is None:
        return False
    prev = row.active
    row.active = bool(active)
    if prev != row.active:
        logger.info(
            "Blacklist %d active %s -> %s (kind=%s value=%r)",
            blacklist_id,
            prev,
            row.active,
            row.kind,
            row.value,
        )
    return True


_BLACKLIST_FIELD_UNSET = object()


class BlacklistUpdateError(ValueError):
    """Soft-validation ошибка inline-edit'а blacklist'а."""


async def update_blacklist(
    session: AsyncSession,
    blacklist_id: int,
    *,
    value=_BLACKLIST_FIELD_UNSET,
    reason=_BLACKLIST_FIELD_UNSET,
) -> bool:
    """Partial update for value/reason. Sentinel `_BLACKLIST_FIELD_UNSET`
    отличает «не передали» от «передали None» — `reason` может быть
    NULL'ом (пустая причина), и UI должен иметь возможность это сохранить.

    Raises ``BlacklistUpdateError`` если value передан и оказался пустой
    после strip — пустое value семантически бесполезно (никогда ни с чем
    не совпадёт), плюс пользователь не сможет визуально отличить
    очищенный ряд от placeholder'а.

    Returns False if the row is missing. Caller wraps in
    ``session.begin()``.

    TODO: дедуп с другими активными рядами того же `kind` — сейчас можно
    инлайн-эдитом сделать (kind=hr, value=@x) дублем, хотя
    `contacts_add_hr_to_blacklist` для add-flow это не даёт. Добавить
    проверку `select(...).where(kind == row.kind, value == new_value,
    id != row.id)` и кидать ``BlacklistUpdateError("Уже существует")``.
    """
    row = await session.get(Blacklist, blacklist_id)
    if row is None:
        return False
    if value is not _BLACKLIST_FIELD_UNSET:
        normalized_value = (value or "").strip()
        if not normalized_value:
            raise BlacklistUpdateError("Значение не может быть пустым.")
        row.value = normalized_value
    if reason is not _BLACKLIST_FIELD_UNSET:
        normalized_reason = (reason or "").strip()
        row.reason = normalized_reason or None
    return True


async def create_blacklist(
    session: AsyncSession,
    *,
    kind: str,
    value: str,
    reason: str | None = None,
) -> tuple[Blacklist, bool]:
    """Insert a blacklist row, дедупликация по (kind, value).

    Если строка с теми же (kind, value) уже есть:
    - active=True → возвращаем её как есть, created=False
    - active=False → ре-активируем и возвращаем, created=False

    Иначе вставляем новую с active=True, created=True.

    Returns (row, created). Caller wraps in ``session.begin()``.
    """
    normalized_value = (value or "").strip()
    if not normalized_value:
        raise BlacklistUpdateError("Значение не может быть пустым.")
    normalized_kind = (kind or "").strip()
    if not normalized_kind:
        raise BlacklistUpdateError("Тип обязателен.")
    normalized_reason = (reason or "").strip() if reason is not None else None
    if normalized_reason == "":
        normalized_reason = None

    existing = (
        await session.scalars(
            select(Blacklist).where(
                Blacklist.kind == normalized_kind,
                Blacklist.value == normalized_value,
            )
        )
    ).first()
    if existing is not None:
        if not existing.active:
            existing.active = True
            logger.info(
                "Blacklist reactivated id=%d kind=%s value=%r",
                existing.id,
                normalized_kind,
                normalized_value,
            )
        if normalized_reason and not existing.reason:
            existing.reason = normalized_reason
        return existing, False

    row = Blacklist(
        kind=normalized_kind,
        value=normalized_value,
        reason=normalized_reason,
        active=True,
    )
    session.add(row)
    await session.flush()
    logger.info(
        "Blacklist created id=%d kind=%s value=%r reason=%r",
        row.id,
        normalized_kind,
        normalized_value,
        normalized_reason,
    )
    return row, True


async def delete_blacklist(
    session: AsyncSession, blacklist_id: int
) -> bool:
    """Delete a blacklist row. Returns False if the row is missing.
    Blacklist — leaf-таблица, никаких FK на неё; delete простой.
    Caller wraps в ``session.begin()``.
    """
    row = await session.get(Blacklist, blacklist_id)
    if row is None:
        return False
    logger.info(
        "Blacklist deleted id=%d kind=%s value=%r",
        blacklist_id,
        row.kind,
        row.value,
    )
    await session.delete(row)
    return True


async def list_blacklist_candidates(
    session: AsyncSession, kind: str
) -> list[dict]:
    """Список options для combobox'а add-modal'а blacklist'а.

    Returns: [{value, label, sub?}], отсортировано по label.

    - kind="hr": HRs с @username или telegram_user_id (что-то для
      сохранения как blacklist value).
    - kind="company": все компании by name.
    - kind="channel": каналы с @username.
    - kind="keyword": [] (свободный ввод).
    """
    if kind == "hr":
        rows = (
            await session.scalars(
                select(HR).where(
                    or_(HR.telegram_username.is_not(None), HR.telegram_user_id.is_not(None))
                )
            )
        ).all()
        out: list[dict] = []
        for hr in rows:
            value = hr_blacklist_preferred_value(hr)
            if value is None:
                continue
            label = hr.name or value
            sub = value if hr.name else None
            out.append({"value": value, "label": label, "sub": sub})
        out.sort(key=lambda x: (x["label"] or "").casefold())
        return out
    if kind == "company":
        rows = (
            await session.scalars(select(Company).order_by(Company.name.asc()))
        ).all()
        return [
            {"value": co.name, "label": co.name, "sub": co.website or None}
            for co in rows if co.name
        ]
    if kind == "channel":
        rows = (
            await session.scalars(
                select(TelegramChannel).where(TelegramChannel.username.is_not(None))
            )
        ).all()
        out = []
        for ch in rows:
            value = channel_blacklist_preferred_value(ch)
            if value is None:
                continue
            label = ch.title or value
            sub = value if ch.title else None
            out.append({"value": value, "label": label, "sub": sub})
        out.sort(key=lambda x: (x["label"] or "").casefold())
        return out
    return []


def _stats_period_since(period: str) -> datetime | None:
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
    since = _stats_period_since(period)

    in_progress_set = {VacancyStatus.INVITATION, VacancyStatus.TEST}

    base_filter = [Vacancy.is_parsed.is_(True)]

    total = int((await session.execute(
        select(func.count(Vacancy.id)).where(*base_filter)
    )).scalar_one())

    applied_total = int((await session.execute(
        select(func.count(func.distinct(VacancyStatusHistory.vacancy_id))).where(
            VacancyStatusHistory.status == VacancyStatus.APPLIED,
        )
    )).scalar_one())

    in_progress_total = int((await session.execute(
        select(func.count(func.distinct(VacancyStatusHistory.vacancy_id))).where(
            VacancyStatusHistory.status.in_(in_progress_set),
        )
    )).scalar_one())

    offer_total = int((await session.execute(
        select(func.count(func.distinct(VacancyStatusHistory.vacancy_id))).where(
            VacancyStatusHistory.status == VacancyStatus.OFFER,
        )
    )).scalar_one())

    decline_total = int((await session.execute(
        select(func.count(func.distinct(VacancyStatusHistory.vacancy_id))).where(
            VacancyStatusHistory.status == VacancyStatus.DECLINE,
        )
    )).scalar_one())

    if since is not None:
        period_filter = [*base_filter, Vacancy.created_at >= since]
        total_period = int((await session.execute(
            select(func.count(Vacancy.id)).where(*period_filter)
        )).scalar_one())

        async def _first_in_period(statuses) -> int:
            cond = (
                VacancyStatusHistory.status.in_(statuses)
                if isinstance(statuses, (set, list, tuple))
                else VacancyStatusHistory.status == statuses
            )
            sub = (
                select(
                    VacancyStatusHistory.vacancy_id.label("vid"),
                    func.min(VacancyStatusHistory.changed_at).label("first_at"),
                )
                .where(cond)
                .group_by(VacancyStatusHistory.vacancy_id)
                .subquery()
            )
            return int((await session.execute(
                select(func.count(sub.c.vid)).where(sub.c.first_at >= since)
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
    since = _stats_period_since(period)
    base = select(Vacancy.status, func.count(Vacancy.id)).where(
        Vacancy.is_parsed.is_(True)
    )
    if since is not None:
        base = base.where(Vacancy.created_at >= since)
    rows = (await session.execute(base.group_by(Vacancy.status))).all()
    counts: dict[str, int] = {s.value: 0 for s in VacancyStatus}
    for status_enum, cnt in rows:
        counts[status_enum.value] = int(cnt or 0)
    return {"period": period, "counts": counts}


async def get_stats_channels_pipeline(
    session: AsyncSession, *, period: str
) -> dict:
    """Per-channel pipeline-таблица для карточки «Каналы».

    Ингест-колонки (по `Vacancy.created_at >= since`):
      - total: всё, что канал прислал в окно (Vacancy-ряды + trash_events)
      - trash: auto-ingest deletions (`trash_event`) + ряды с
        `status=NOT_FIT` и `skip_reason LIKE 'trash:%'` (rerun-режим)
      - not_fit: `status=NOT_FIT` БЕЗ trash-маркера (отсев фит-валидатором)
      - fit = max(0, total − trash − not_fit)

    Funnel-колонки (по `min(changed_at) >= since` — distinct vacancy_id,
    у которых ПЕРВЫЙ переход в соответствующий набор статусов случился
    в окне period; для period='all' — лайфтайм без фильтра по времени):
      - sent: первый переход в Applied
      - answered: первый переход в любой из
        {Answered, Test, Invitation, In Progress, Offer, Decline}
      - invite_plus: первый переход в {Invitation, In Progress, Offer}
      - decline: первый переход в Decline
      - conv_answ_sent = answered/sent (None если sent=0)
      - conv_invite_sent = invite_plus/sent (None если sent=0)

    Канал попадает в таблицу, если в окне есть хоть что-то: ингест,
    trash-event или funnel-активность.

    Сортировка: по total desc, тай-брейкер по label.
    """
    since = _stats_period_since(period)
    base_filter = [Vacancy.is_parsed.is_(True)]
    if since is not None:
        base_filter.append(Vacancy.created_at >= since)

    # Шаг 1: total / trash / not_fit per channel.
    #
    # «Trash» — посты, отсеянные LLM-валидатором как мусор. В auto-ingest
    # режиме они УДАЛЯЮТСЯ из ``vacancy``, и счётчик хранится в отдельной
    # таблице ``trash_event`` (см. _delete_vacancy_as_trash в flows.py).
    # В rerun-режиме ряд остаётся как ``status=NOT_FIT`` + ``skip_reason``
    # начинается с "trash:" — таких добавим к trash-счётчику ниже.
    # Not Fit (clean) — отсев фит-валидатором по языку/локации/уровню,
    # т.е. ``status=NOT_FIT`` БЕЗ trash-маркера в skip_reason.
    is_rerun_trash = and_(
        Vacancy.status == VacancyStatus.NOT_FIT,
        Vacancy.skip_reason.like("trash:%"),
    )
    is_not_fit_clean = and_(
        Vacancy.status == VacancyStatus.NOT_FIT,
        or_(
            Vacancy.skip_reason.is_(None),
            ~Vacancy.skip_reason.like("trash:%"),
        ),
    )
    rows = (
        await session.execute(
            select(
                TelegramChannel.id,
                TelegramChannel.title,
                TelegramChannel.username,
                func.count(Vacancy.id).label("total"),
                func.sum(case((is_rerun_trash, 1), else_=0)).label("rerun_trash"),
                func.sum(case((is_not_fit_clean, 1), else_=0)).label("not_fit"),
            )
            .join(Vacancy, Vacancy.source_channel_id == TelegramChannel.id)
            .where(*base_filter)
            .group_by(TelegramChannel.id)
        )
    ).all()

    # Шаг 1b: trash-events за period (auto-ingest deletions). Per-channel
    # COUNT(*) по той же временной рамке, что и Vacancy.created_at.
    trash_event_filter = []
    if since is not None:
        trash_event_filter.append(TrashEvent.created_at >= since)
    trash_events_rows = (
        await session.execute(
            select(
                TrashEvent.source_channel_id,
                func.count(TrashEvent.id),
            )
            .where(*trash_event_filter)
            .group_by(TrashEvent.source_channel_id)
        )
    ).all()
    trash_events_by_ch: dict[int, int] = {}
    for ch_id, cnt in trash_events_rows:
        if ch_id is not None:
            trash_events_by_ch[ch_id] = int(cnt or 0)

    # Шаг 2: history-based «sent / answered / invite+ / decline» per channel.
    # Distinct vacancy_id, у которых ПЕРВЫЙ переход в нужный набор статусов
    # (min(changed_at)) попал в окно period. Привязка к самому факту
    # перехода, а не к Vacancy.created_at — чтобы funnel показывал именно
    # «прогресс за период», совпадая с верхним KPI-блоком.
    answered_set = {
        VacancyStatus.ANSWERED, VacancyStatus.TEST, VacancyStatus.INVITATION,
        VacancyStatus.IN_PROGRESS, VacancyStatus.OFFER, VacancyStatus.DECLINE,
    }
    invite_set = {
        VacancyStatus.INVITATION, VacancyStatus.IN_PROGRESS, VacancyStatus.OFFER,
    }

    async def _first_in_period_by_channel(statuses) -> dict[int, set[int]]:
        cond = (
            VacancyStatusHistory.status.in_(statuses)
            if isinstance(statuses, (set, list, tuple))
            else VacancyStatusHistory.status == statuses
        )
        sub = (
            select(
                VacancyStatusHistory.vacancy_id.label("vid"),
                func.min(VacancyStatusHistory.changed_at).label("first_at"),
            )
            .where(cond)
            .group_by(VacancyStatusHistory.vacancy_id)
            .subquery()
        )
        q = (
            select(Vacancy.source_channel_id, sub.c.vid)
            .join(sub, sub.c.vid == Vacancy.id)
            .where(Vacancy.is_parsed.is_(True))
        )
        if since is not None:
            q = q.where(sub.c.first_at >= since)
        by_ch: dict[int, set[int]] = {}
        for ch_id, vid in (await session.execute(q)).all():
            if ch_id is None:
                continue
            by_ch.setdefault(ch_id, set()).add(vid)
        return by_ch

    sent_by_ch = await _first_in_period_by_channel(VacancyStatus.APPLIED)
    answered_by_ch = await _first_in_period_by_channel(answered_set)
    invite_by_ch = await _first_in_period_by_channel(invite_set)
    decline_by_ch = await _first_in_period_by_channel(VacancyStatus.DECLINE)

    # Сводим. Канал должен попасть в таблицу, если в окне периода у него
    # есть хоть что-то: Vacancy-ряды (ингест), TrashEvent (auto-deletions)
    # или funnel-активность (старая вакансия впервые перешла в нужный
    # статус внутри окна).
    items_by_ch: dict[int, dict] = {}
    for ch_id, title, username, total_vac, rerun_trash, not_fit in rows:
        items_by_ch[ch_id] = {
            "id": ch_id,
            "label": title or (f"@{username}" if username else f"#{ch_id}"),
            "_total_vac": int(total_vac or 0),
            "_rerun_trash": int(rerun_trash or 0),
            "not_fit": int(not_fit or 0),
        }
    needed_ch_ids: set[int] = set()
    needed_ch_ids.update(trash_events_by_ch.keys())
    needed_ch_ids.update(sent_by_ch.keys())
    needed_ch_ids.update(answered_by_ch.keys())
    needed_ch_ids.update(invite_by_ch.keys())
    needed_ch_ids.update(decline_by_ch.keys())
    orphan_ids = [c for c in needed_ch_ids if c not in items_by_ch]
    if orphan_ids:
        orphan_rows = (
            await session.execute(
                select(TelegramChannel.id, TelegramChannel.title, TelegramChannel.username)
                .where(TelegramChannel.id.in_(orphan_ids))
            )
        ).all()
        for ch_id, title, username in orphan_rows:
            items_by_ch[ch_id] = {
                "id": ch_id,
                "label": title or (f"@{username}" if username else f"#{ch_id}"),
                "_total_vac": 0,
                "_rerun_trash": 0,
                "not_fit": 0,
            }
    if not items_by_ch:
        return {"period": period, "channels": []}

    items = []
    for ch_id, item in items_by_ch.items():
        trash_events = trash_events_by_ch.get(ch_id, 0)
        # total = всё что канал «прислал» за period: Vacancy-ряды + trash_events
        # (auto-ingest deletions, которых уже нет в vacancy table)
        total = item["_total_vac"] + trash_events
        # Полный trash = удалённые auto-ingest + помеченные rerun
        trash = trash_events + item["_rerun_trash"]
        not_fit = item["not_fit"]
        fit = max(0, total - trash - not_fit)
        sent = len(sent_by_ch.get(ch_id, set()))
        answered = len(answered_by_ch.get(ch_id, set()))
        invite_plus = len(invite_by_ch.get(ch_id, set()))
        decline = len(decline_by_ch.get(ch_id, set()))
        conv_answ = (answered / sent * 100) if sent > 0 else None
        conv_invite = (invite_plus / sent * 100) if sent > 0 else None
        items.append({
            "id": ch_id,
            "label": item["label"],
            "total": total,
            "trash": trash,
            "not_fit": not_fit,
            "fit": fit,
            "sent": sent,
            "answered": answered,
            "invite_plus": invite_plus,
            "decline": decline,
            "conv_answ_sent": (round(conv_answ, 1) if conv_answ is not None else None),
            "conv_invite_sent": (round(conv_invite, 1) if conv_invite is not None else None),
        })
    items.sort(key=lambda it: (-it["total"], it["label"].casefold()))
    return {"period": period, "channels": items}


async def get_stats_skills(
    session: AsyncSession, *, period: str, limit: int = 27, min_count: int = 2,
) -> dict:
    """Топ-N технологий из `Vacancy.stack` за period с маркировкой
    «есть в моём профиле».

    - Считаем частоту по casefold-канону (одна технология = один счётчик
      даже если в посте написана «Python» / «python» / «PYTHON»).
    - Дедупликация в рамках одной вакансии: «Python» в стеке два раза
      = +1, не +2.
    - mine = canon ∈ profile_set, где profile_set — casefold(name) +
      casefold(aliases) для всех `ProfileSkill`.
    - Фильтруем шум: показываем теги с count >= ``min_count`` (по умолч. 2).
      Топ-N по count desc, тай-брейкер casefold.
    """
    since = _stats_period_since(period)
    base_filter = [Vacancy.is_parsed.is_(True), Vacancy.stack.is_not(None)]
    if since is not None:
        base_filter.append(Vacancy.created_at >= since)

    skill_rows = (await session.scalars(select(ProfileSkill))).all()
    profile_set: set[str] = set()
    for s in skill_rows:
        if s.name:
            profile_set.add(s.name.strip().casefold())
        if s.aliases:
            for a in s.aliases:
                if isinstance(a, str) and a.strip():
                    profile_set.add(a.strip().casefold())

    rows = (
        await session.scalars(select(Vacancy.stack).where(*base_filter))
    ).all()
    counts: dict[str, int] = {}
    canon_by_lower: dict[str, str] = {}
    for stack in rows:
        if not isinstance(stack, list):
            continue
        seen_in_row: set[str] = set()
        for item in stack:
            if not isinstance(item, str):
                continue
            tag = item.strip()
            if not tag:
                continue
            lo = tag.casefold()
            if lo in seen_in_row:
                continue
            seen_in_row.add(lo)
            canon = canon_by_lower.setdefault(lo, tag)
            counts[canon] = counts.get(canon, 0) + 1

    items = []
    for canon, cnt in counts.items():
        if cnt < min_count:
            continue
        items.append({
            "label": canon,
            "count": cnt,
            "mine": canon.casefold() in profile_set,
        })
    items.sort(key=lambda it: (-it["count"], it["label"].casefold()))
    return {
        "period": period,
        "min_count": min_count,
        "skills": items[:limit],
    }


async def get_stats_hr_responses(
    session: AsyncSession, *, period: str
) -> dict:
    """HR-response-time + weekday-распределение ответов.

    Алгоритм:
      1. На вход берём вакансии, у которых ПЕРВЫЙ переход в Applied
         случился внутри `period` (по `VacancyStatusHistory.changed_at`).
         Это «application-window» — ровно те отклики, которые мы делали в
         этот период.
      2. Для каждой такой вакансии ищем первый incoming-Message с
         `sent_at > applied_at` — реальный ответ HR (Telegram-сообщение).
         Берём `Message.sent_at` (когда HR нажал «отправить»), а не
         `created_at` (когда наш бот сохранил), чтобы weekday отражал
         именно «когда HR живой».
      3. Метрики:
         - by_weekday: распределение first-response.sent_at по дням
           недели (0=Пн … 6=Вс)
         - median_seconds: median(first_response_sent_at − applied_at)
           среди тех, кто ответил
         - no_response_pct: процент applied вакансий БЕЗ first-response
         - applied_count / responded_count: голые числа
    """
    since = _stats_period_since(period)

    # Шаг 1: первый Applied на каждую vacancy, ограниченный period
    first_applied_subq = (
        select(
            VacancyStatusHistory.vacancy_id.label("vid"),
            func.min(VacancyStatusHistory.changed_at).label("applied_at"),
        )
        .where(VacancyStatusHistory.status == VacancyStatus.APPLIED)
        .group_by(VacancyStatusHistory.vacancy_id)
        .subquery()
    )
    where_clauses = []
    if since is not None:
        where_clauses.append(first_applied_subq.c.applied_at >= since)
    applied_rows = (
        await session.execute(
            select(first_applied_subq.c.vid, first_applied_subq.c.applied_at)
            .where(*where_clauses)
        )
    ).all()
    if not applied_rows:
        return {
            "period": period,
            "by_weekday": [0, 0, 0, 0, 0, 0, 0],
            "median_seconds": None,
            "no_response_pct": None,
            "applied_count": 0,
            "responded_count": 0,
        }

    # Шаг 2 + 3: для каждой vacancy ищем первый incoming-Message после
    # applied_at и копим weekday/delta. Bulk-запрос, чтобы не делать
    # N round-trips: тянем все incoming Message'ы и группируем в Python
    # (выборки маленькие — десятки/сотни вакансий).
    applied_map = {vid: applied_at for vid, applied_at in applied_rows}
    msg_rows = (
        await session.execute(
            select(Message.vacancy_id, Message.sent_at)
            .where(
                Message.vacancy_id.in_(applied_map.keys()),
                Message.is_incoming.is_(True),
                Message.is_deleted.is_(False),
            )
        )
    ).all()
    first_resp_by_vid: dict[int, datetime] = {}
    for vid, sent_at in msg_rows:
        if sent_at is None:
            continue
        applied_at = applied_map.get(vid)
        if applied_at is None or sent_at <= applied_at:
            continue
        cur = first_resp_by_vid.get(vid)
        if cur is None or sent_at < cur:
            first_resp_by_vid[vid] = sent_at

    by_weekday = [0, 0, 0, 0, 0, 0, 0]  # Пн=0 … Вс=6 (Python weekday())
    deltas: list[float] = []
    for vid, applied_at in applied_map.items():
        resp_ts = first_resp_by_vid.get(vid)
        if resp_ts is None:
            continue
        by_weekday[resp_ts.weekday()] += 1
        delta = (resp_ts - applied_at).total_seconds()
        if delta > 0:
            deltas.append(delta)
    deltas.sort()

    median_seconds: float | None
    if deltas:
        n = len(deltas)
        if n % 2 == 1:
            median_seconds = float(deltas[n // 2])
        else:
            median_seconds = (deltas[n // 2 - 1] + deltas[n // 2]) / 2
    else:
        median_seconds = None

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


async def list_blacklist(session: AsyncSession) -> list[Blacklist]:
    """Все строки blacklist'а одним запросом — список обычно <100, нет
    смысла гонять SQL-фильтры. UI фильтрует локально по kind и поиску.

    Order: insertion order (id ASC). Раньше сортировали по active+created
    desc — но при toggle активности ряд прыгал между верхом и низом, что
    путало пользователя. Стабильный порядок по id важнее визуальной
    группировки.
    """
    rows = (
        await session.scalars(
            select(Blacklist).order_by(Blacklist.id.asc())
        )
    ).all()
    return list(rows)


async def find_channel_by_username(
    session: AsyncSession, username: str
) -> TelegramChannel | None:
    """Locate an existing channel by @username, case-insensitive.

    Telegram treats usernames as case-insensitive — `@MyChan` and `@mychan`
    refer to the same channel. Existing rows in the DB могут быть с
    разным регистром (исторически сидились через сырой SQL), поэтому
    сравниваем через ``LOWER()``.
    """
    return (
        await session.scalars(
            select(TelegramChannel).where(
                func.lower(TelegramChannel.username) == username.lower()
            )
        )
    ).first()


async def set_channel_active(
    session: AsyncSession, channel_id: int, is_active: bool
) -> bool:
    """Toggle TelegramChannel.is_active. Returns False if the row is missing.

    Caller wraps in ``session.begin()``; only a single row mutation here so
    no extra invariants to enforce.
    """
    ch = await session.get(TelegramChannel, channel_id)
    if ch is None:
        return False
    prev = ch.is_active
    ch.is_active = bool(is_active)
    if prev != ch.is_active:
        logger.info(
            "Channel %d (@%s) is_active %s -> %s",
            channel_id,
            ch.username,
            prev,
            ch.is_active,
        )
    return True


async def deactivate_blacklisted_channels(session: AsyncSession) -> int:
    """Set is_active=False для всех каналов, чьи blacklist-кандидаты
    совпадают с активной строкой kind=channel. Idempotent: уже-выключенные
    не трогаем. Returns count flipped — для логов/тостов.

    Зеркалит matching-логику ``list_telegram_channels._is_blacklisted``
    (exact match, case-sensitive). Caller wraps в ``session.begin()``.
    """
    bl_values = set(
        (
            await session.scalars(
                select(Blacklist.value).where(
                    Blacklist.kind == "channel",
                    Blacklist.active.is_(True),
                )
            )
        ).all()
    )
    if not bl_values:
        return 0
    channels = (
        await session.scalars(
            select(TelegramChannel).where(TelegramChannel.is_active.is_(True))
        )
    ).all()
    flipped = 0
    for ch in channels:
        if any(c in bl_values for c in channel_blacklist_candidates(ch)):
            ch.is_active = False
            flipped += 1
    if flipped:
        logger.info("Deactivated %d channel(s) by blacklist", flipped)
    return flipped


async def is_channel_blacklisted(
    session: AsyncSession, channel_id: int
) -> bool:
    """True если в blacklist'е активна строка kind=channel, value которой
    совпадает с одним из blacklist-кандидатов канала. Используется в
    set_channel_active для отказа re-enable'а.
    """
    ch = await session.get(TelegramChannel, channel_id)
    if ch is None:
        return False
    return await _channel_blacklist_value(session, ch) is not None


async def set_all_channels_active(
    session: AsyncSession, is_active: bool
) -> int:
    """Bulk-flip every TelegramChannel.is_active to the same value.
    Returns row count for the toast. Caller wraps in ``session.begin()``.

    При is_active=True пропускаем каналы, попавшие в blacklist — их
    нельзя включить никаким образом, в т.ч. через «Включить все».
    """
    stmt = update(TelegramChannel).values(is_active=bool(is_active))
    if is_active:
        bl_values = list(
            (
                await session.scalars(
                    select(Blacklist.value).where(
                        Blacklist.kind == "channel",
                        Blacklist.active.is_(True),
                    )
                )
            ).all()
        )
        if bl_values:
            # Совпадение по `@username` — то же exact-match, что в
            # `channel_blacklist_candidates`.
            stripped = [v.lstrip("@") for v in bl_values]
            stmt = stmt.where(TelegramChannel.username.notin_(stripped))
    result = await session.execute(stmt)
    affected = int(result.rowcount or 0)
    logger.info(
        "Bulk channel toggle is_active=%s, affected=%d",
        bool(is_active),
        affected,
    )
    return affected


async def reset_channel_cursor(session: AsyncSession, channel_id: int) -> bool:
    """Clear ``last_processed_msg_id`` so the next poll re-pulls recent
    history. Returns False if the row is missing.
    """
    ch = await session.get(TelegramChannel, channel_id)
    if ch is None:
        return False
    ch.last_processed_msg_id = None
    return True


async def delete_channel(
    session: AsyncSession, channel_id: int
) -> int | None:
    """Delete a channel. Severs the FK on existing vacancies (sets
    ``source_channel_id = NULL``) so we don't lose forensic data — the
    raw_text + LLM-parsed fields stay searchable, just without the
    channel link. Returns the count of detached vacancies, or None if
    the channel didn't exist.
    """
    ch = await session.get(TelegramChannel, channel_id)
    if ch is None:
        return None
    ch_username = ch.username
    detached = (
        await session.execute(
            update(Vacancy)
            .where(Vacancy.source_channel_id == channel_id)
            .values(source_channel_id=None)
        )
    ).rowcount
    # TrashEvent держит ondelete=SET NULL — PRAGMA foreign_keys=ON
    # (adapters/db.py) сделает это автоматически при session.delete(ch).
    # Дублирующий UPDATE — defense-in-depth: если FK по какой-то причине
    # disabled (dev sqlite3 CLI / отсутствие listener'а), события не
    # останутся «висячими» с указателем на удалённый канал.
    detached_trash = (
        await session.execute(
            update(TrashEvent)
            .where(TrashEvent.source_channel_id == channel_id)
            .values(source_channel_id=None)
        )
    ).rowcount
    await session.delete(ch)
    detached_n = int(detached or 0)
    detached_trash_n = int(detached_trash or 0)
    logger.info(
        "Deleted channel %d (@%s), detached %d vacancies, %d trash events",
        channel_id,
        ch_username,
        detached_n,
        detached_trash_n,
    )
    return detached_n


def company_blacklist_candidates(co: Company) -> list[str]:
    """Possible blacklist `value` strings that should match this company.

    Just the company name — no other identifiers exist (no @username
    equivalent for companies). Returned as a list to mirror the HR helper
    so callers can use the same `value.in_(candidates)` shape.
    """
    return [co.name] if co.name else []


def company_blacklist_preferred_value(co: Company) -> str | None:
    return co.name or None


async def _company_blacklist_value(
    session: AsyncSession, co: Company
) -> str | None:
    candidates = company_blacklist_candidates(co)
    if not candidates:
        return None
    row = (
        await session.scalars(
            select(Blacklist)
            .where(
                Blacklist.kind == "company",
                Blacklist.value.in_(candidates),
                Blacklist.active.is_(True),
            )
            .order_by(Blacklist.id.asc())
            .limit(1)
        )
    ).first()
    return row.value if row else None


async def get_company_detail(
    session: AsyncSession, company_id: int
) -> "CompanyDetail | None":
    """Detail payload for the Contacts/Companies pane (06): company row +
    vacancy count + distinct HR count + blacklist status.
    """
    co = await session.get(Company, company_id)
    if co is None:
        return None
    vacancy_count = int(
        await session.scalar(
            select(func.count(Vacancy.id)).where(Vacancy.company_id == company_id)
        )
        or 0
    )
    hr_count = int(
        await session.scalar(
            select(func.count(func.distinct(Vacancy.hr_id))).where(
                Vacancy.company_id == company_id,
                Vacancy.hr_id.is_not(None),
            )
        )
        or 0
    )
    blacklist_value = await _company_blacklist_value(session, co)
    return CompanyDetail(
        company=co,
        vacancy_count=vacancy_count,
        hr_count=hr_count,
        blacklist_value=blacklist_value,
    )


async def list_vacancies_for_company(
    session: AsyncSession, company_id: int
) -> list[Vacancy]:
    """All parsed vacancies linked to this company, newest-first."""
    rows = (
        await session.scalars(
            select(Vacancy)
            .where(Vacancy.company_id == company_id, Vacancy.is_parsed.is_(True))
            .order_by(Vacancy.created_at.desc(), Vacancy.id.desc())
        )
    ).all()
    return list(rows)


# Channel mini-list sort order — UI requirement: hottest funnel statuses
# first (Offer / In Progress / Invitation / Test / Answered / Applied / New),
# then unresolved cold (Scam / Ghosting / Decline), then NotFit at the
# bottom. Secondary sort внутри одного статуса — по дате появления вакансии
# (posted_at если есть, иначе created_at), новые сверху.
#
# Ключи — .value-строки, а не enum-члены: при `case(dict, value=col)` SA
# биндит ключи как литералы БЕЗ прогона через Enum-type processor колонки,
# и aiosqlite падает с `type 'VacancyStatus' is not supported`. Падение
# проглатывалось в `_dispatch` как _err, и мини-список рендерил «нет
# вакансий», хотя badge/funnel показывали реальный count.
_CHANNEL_VAC_STATUS_RANK: dict[str, int] = {
    VacancyStatus.OFFER.value: 1,
    VacancyStatus.IN_PROGRESS.value: 2,
    VacancyStatus.INVITATION.value: 3,
    VacancyStatus.TEST.value: 4,
    VacancyStatus.ANSWERED.value: 5,
    VacancyStatus.APPLIED.value: 6,
    VacancyStatus.NEW.value: 7,
    VacancyStatus.SCAM.value: 8,
    VacancyStatus.GHOSTING.value: 9,
    VacancyStatus.DECLINE.value: 10,
    VacancyStatus.NOT_FIT.value: 11,
}


async def list_vacancies_for_channel(
    session: AsyncSession,
    channel_id: int,
    *,
    limit: int = 50,
    offset: int = 0,
) -> list[Vacancy]:
    """Все вакансии из канала, sorted by status priority then by recency.
    Pagination via limit/offset — каналы могут накапливать тысячи вакансий,
    мини-список в detail-pane грузит их пачками.

    is_parsed-фильтр НЕ применяем: badge канала и stats-блок считают все
    вакансии (без этого фильтра), и фильтрация мини-списка по is_parsed=True
    создавала рассинхрон — count=14, stats=14, мини-список пустой. Это
    случается в том числе у пользователей со старыми данными до миграции
    df83674 (`is_parsed` появился позже, существующие parsed-ряды получили
    дефолт False, и `recover_orphan_vacancies` не всегда успевает их
    восстановить — например, без активного бота). Половинно-построенные
    ряды (только raw_text) рендерятся как «— без названия —» через
    существующий fallback в UI.
    """
    status_rank = case(
        _CHANNEL_VAC_STATUS_RANK,
        value=Vacancy.status,
        else_=99,
    )
    activity = func.coalesce(Vacancy.posted_at, Vacancy.created_at)
    rows = (
        await session.scalars(
            select(Vacancy)
            .where(Vacancy.source_channel_id == channel_id)
            .order_by(status_rank.asc(), activity.desc(), Vacancy.id.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return list(rows)


async def list_hrs_for_company(
    session: AsyncSession, company_id: int
) -> list[tuple[HR, int]]:
    """Distinct HRs that have at least one vacancy at this company, with
    the count of vacancies they brought to it. Ordered by count desc.
    """
    rows = (
        await session.execute(
            select(HR, func.count(Vacancy.id).label("cnt"))
            .join(Vacancy, Vacancy.hr_id == HR.id)
            .where(Vacancy.company_id == company_id)
            .group_by(HR.id)
            .order_by(func.count(Vacancy.id).desc(), HR.name.asc())
        )
    ).all()
    return [(hr, int(cnt or 0)) for hr, cnt in rows]


_COMPANY_FIELD_UNSET = object()


async def update_company_fields(
    session: AsyncSession,
    company_id: int,
    *,
    name=_COMPANY_FIELD_UNSET,
    website=_COMPANY_FIELD_UNSET,
    aliases=_COMPANY_FIELD_UNSET,
    notes=_COMPANY_FIELD_UNSET,
) -> bool:
    """Patch one or more Company columns. Sentinel-default unset = leave
    unchanged. Returns False if the company id isn't found.
    """
    co = await session.get(Company, company_id)
    if co is None:
        return False
    changed = []
    if name is not _COMPANY_FIELD_UNSET:
        cleaned = (str(name).strip() if name is not None else "")
        if not cleaned:
            return False  # company name is required (UNIQUE NOT NULL)
        co.name = cleaned
        changed.append("name")
    if website is not _COMPANY_FIELD_UNSET:
        co.website = (
            (str(website).strip() or None) if website is not None else None
        )
        changed.append("website")
    if aliases is not _COMPANY_FIELD_UNSET:
        # Accept list-of-str only; normalize: strip + dedup + drop empty.
        seen = set()
        cleaned_list: list[str] = []
        for a in (aliases or []):
            if not isinstance(a, str):
                continue
            s = a.strip()
            if s and s.casefold() not in seen:
                seen.add(s.casefold())
                cleaned_list.append(s)
        co.aliases = cleaned_list
        changed.append("aliases")
    if notes is not _COMPANY_FIELD_UNSET:
        co.notes = (
            (str(notes).strip() or None) if notes is not None else None
        )
        changed.append("notes")
    await session.flush()
    if changed:
        logger.debug("Updated company %d fields=%s", company_id, changed)
    return True


async def delete_company(session: AsyncSession, company_id: int) -> bool:
    """Drop the company; vacancies survive with ``company_id = NULL``.

    Mirrors ``delete_hr``'s SET-NULL-on-vacancies stance: a vacancy is
    intrinsic to its source channel, not to the company tag we attached.
    Caller commits.
    """
    co = await session.get(Company, company_id)
    if co is None:
        return False
    co_name = co.name
    detached = (
        await session.execute(
            update(Vacancy)
            .where(Vacancy.company_id == company_id)
            .values(company_id=None)
        )
    ).rowcount
    await session.delete(co)
    logger.info(
        "Deleted company %d (%r), detached %d vacancies",
        company_id,
        co_name,
        int(detached or 0),
    )
    return True


async def add_vacancy_event(
    session: AsyncSession,
    vacancy_id: int,
    kind: str,
    payload: dict | None = None,
) -> VacancyEvent:
    """Append a non-status event to the timeline (parsed, ingested, rerun, ...).

    Status changes go to ``vacancy_status_history`` instead. Caller wraps
    in ``session.begin()``.
    """
    event = VacancyEvent(
        vacancy_id=vacancy_id,
        kind=kind,
        payload=(payload or None),
    )
    session.add(event)
    await session.flush()
    return event


async def apply_classification(
    session: AsyncSession,
    vacancy_id: int,
    message_id: int,
    classification: Classification,
) -> None:
    vacancy = await session.get(Vacancy, vacancy_id)
    if vacancy is None:
        logger.warning("apply_classification: vacancy %s not found", vacancy_id)
        return
    previous = vacancy.status
    applied = should_apply_status(previous, classification.status)
    if not applied:
        # Переход не разрешён state-machine'ом (например, classifier
        # выдал Invitation для уже-Decline вакансии). Раньше тут писали
        # призрачную VacancyStatusHistory с applied=False — она вылезала
        # в timeline отдельной строкой и сбивала с толку. Теперь не
        # пишем ничего: входящий DM уже сохранён как Message выше по
        # стеку, этого аудит-следа достаточно.
        logger.info(
            "vacancy %d: classifier verdict %s blocked by state-machine "
            "(current=%s, msg=%d) — no history row written",
            vacancy_id,
            classification.status.value,
            previous.value if previous else None,
            message_id,
        )
        return
    vacancy.status = classification.status
    logger.info(
        "vacancy %d: status %s -> %s (auto, msg=%d)",
        vacancy_id,
        previous.value if previous else None,
        classification.status.value,
        message_id,
    )
    session.add(
        VacancyStatusHistory(
            vacancy_id=vacancy_id,
            message_id=message_id,
            previous_status=previous,
            status=classification.status,
            explanation=_ensure_trailing_period(classification.explanation),
            applied=True,
        )
    )


async def mark_ghosted_vacancies(
    session: AsyncSession,
    *,
    timeout_days: int,
) -> list[int]:
    """Сканирует Applied/In Progress вакансии и переводит в Ghosting те,
    у которых HR молчит дольше ``timeout_days``.

    «Молчит» означает: ни одного входящего Message, и сам статус не
    менялся, и вакансия не создавалась в окне последних ``timeout_days``
    дней. Reference timestamp = max(last incoming Message.sent_at,
    last status change в текущий статус, vacancy.created_at).

    Возвращает список vacancy_id, переведённых в Ghosting. Caller
    оборачивает в session.begin() и выполняет commit.
    """
    from datetime import datetime, timedelta, timezone
    from backend.domain import GHOSTING_ELIGIBLE_FROM

    cutoff = datetime.now(timezone.utc) - timedelta(days=timeout_days)
    eligible_status_values = [s for s in GHOSTING_ELIGIBLE_FROM]
    # Один round-trip вместо 1+2N: pre-агрегируем последние таймстампы
    # по vacancy_id (для входящих DM) и по (vacancy_id, status) — для
    # status-history. OUTER JOIN потому, что у новых вакансий ещё может
    # не быть ни сообщений, ни истории.
    last_msg_subq = (
        select(
            Message.vacancy_id.label("vid"),
            func.max(Message.sent_at).label("last_msg_at"),
        )
        .where(Message.is_incoming.is_(True))
        .group_by(Message.vacancy_id)
        .subquery()
    )
    last_status_subq = (
        select(
            VacancyStatusHistory.vacancy_id.label("vid"),
            VacancyStatusHistory.status.label("status"),
            func.max(VacancyStatusHistory.changed_at).label("last_status_at"),
        )
        .group_by(
            VacancyStatusHistory.vacancy_id, VacancyStatusHistory.status
        )
        .subquery()
    )
    rows = (
        await session.execute(
            select(
                Vacancy,
                last_msg_subq.c.last_msg_at,
                last_status_subq.c.last_status_at,
            )
            .outerjoin(last_msg_subq, last_msg_subq.c.vid == Vacancy.id)
            .outerjoin(
                last_status_subq,
                and_(
                    last_status_subq.c.vid == Vacancy.id,
                    last_status_subq.c.status == Vacancy.status,
                ),
            )
            .where(Vacancy.status.in_(eligible_status_values))
        )
    ).all()
    if not rows:
        return []

    affected: list[int] = []
    for v, last_msg_at, last_status_at in rows:
        # Берём максимум из доступных временных меток. created_at
        # есть всегда, остальные могут быть None — фильтруем.
        timestamps = [v.created_at]
        if last_msg_at is not None:
            timestamps.append(last_msg_at)
        if last_status_at is not None:
            timestamps.append(last_status_at)
        last_activity = max(timestamps)
        if last_activity >= cutoff:
            continue
        # Перевод в Ghosting. message_id=None — это системное событие,
        # не привязано к конкретной HR-реплике. source ложится на
        # server_default 'system'.
        previous = v.status
        v.status = VacancyStatus.GHOSTING
        session.add(
            VacancyStatusHistory(
                vacancy_id=v.id,
                message_id=None,
                previous_status=previous,
                status=VacancyStatus.GHOSTING,
                explanation=(
                    f"HR не отвечает более {timeout_days} дней — "
                    "автоматически помечено как ghosting."
                ),
                applied=True,
            )
        )
        affected.append(v.id)
    return affected


# === Company dedup ====================================================
# Трёхступенчатая схема:
#   Stage 1 — детерминированные правила: точное совпадение нормализованного
#             имени / алиаса / хоста сайта (95% случаев).
#   Stage 2 — LLM-арбитр на похожих кандидатах (Левенштейн ≥ 0.7), когда
#             точного правила не сработало, но есть с чем сравнить.
#   Stage 3 — создание новой строки.
# Hard-rule: если у обоих указаны websites и хосты разные — это РАЗНЫЕ
# компании, не мержим даже при совпадении имени/алиаса. Применяется и в
# Stage 1 (фильтр), и в Stage 2 (фильтр shortlist'а до LLM).

# Минимальная транслитерация русского кириллического алфавита в латиницу
# для дедупа имён вида «МТС» / «MTS». Ё → e (как в большинстве passport
# transliteration — для match'а это надёжнее, чем yo).
_CYR_TO_LAT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def _translit_cyr_to_latin(s: str) -> str:
    return "".join(_CYR_TO_LAT.get(ch, ch) for ch in s.lower())


# Юр.формы вырезаются из имени до сравнения: «ПАО Сбербанк» → «sberbank».
# Регистр и кириллица — после lower() и transliterate.
_LEGAL_SUFFIX_RE = re.compile(
    r"\b(pao|oao|ao|zao|ooo|jsc|llc|ltd|inc|corp|gmbh|sa|ag|nv|bv|plc|sas)\b\.?"
)
_QUOTE_CHARS = set("«»\"'`“”„‚‘’")


def _normalize_company_name(s: str | None) -> str:
    """Нормализованная форма имени для deterministic match: lowercase +
    транслитерация + срезанные юр.суффиксы + сглаженные пробелы."""
    if not s:
        return ""
    s = "".join(ch for ch in s.strip() if ch not in _QUOTE_CHARS)
    s = _translit_cyr_to_latin(s)
    s = _LEGAL_SUFFIX_RE.sub(" ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def _normalize_host(url: str | None) -> str:
    """Хост сайта без схемы / www. / порта / пути / query / fragment /
    завершающей точки. Пустая строка для None или невалидного URL.
    Полный host (а не registrable domain) — чтобы `pay.yandex.ru` ≠
    `yandex.ru` (subsidiary trap)."""
    if not url:
        return ""
    s = url.strip().lower()
    s = re.sub(r"^[a-z][a-z0-9+.\-]*://", "", s)
    s = s.lstrip("/")
    # Срезаем path / query / fragment ДО того, как лезть в port:
    # "sber.ru?utm=foo" без strip-а query превратился бы в host
    # "sber.ru?utm=foo" и сломал бы host-match.
    s = s.split("/", 1)[0]
    s = s.split("?", 1)[0]
    s = s.split("#", 1)[0]
    s = s.split(":", 1)[0]
    if s.startswith("www."):
        s = s[4:]
    # FQDN с завершающей точкой ("example.com.") — нормализуем к
    # "example.com", иначе host-match отказывает на пустяковом расхождении.
    s = s.rstrip(".")
    return s


# Хосты, которые НЕ являются «домашним сайтом компании»: агрегаторы
# вакансий, соцсети, мессенджеры, блог-платформы. Если parser ошибся и
# сунул в `company_website` ссылку на канал/профиль/пост, Stage 1c (host-
# match) мог бы склеить две разные компании по этому общему host'у. Для
# таких host'ов host-match пропускается; останутся только name/alias-match
# и Stage 2 LLM.
_AGGREGATOR_HOSTS = frozenset({
    "t.me",
    "telegram.me",
    "telegram.org",
    "linkedin.com",
    "hh.ru",
    "habr.com",
    "vc.ru",
    "github.com",
    "gitlab.com",
    "avito.ru",
    "superjob.ru",
    "facebook.com",
    "instagram.com",
    "twitter.com",
    "x.com",
    "vk.com",
    "ok.ru",
    "youtube.com",
    "behance.net",
    "dribbble.com",
    "medium.com",
    # Шеринговые хостинги job-страниц / резидент-каталоги: на одном
    # хосте сидит много разных компаний → Stage 1c (website-match) на
    # таком общем домене склеит их в одну. Любой *.potok.io,
    # *.huntflow.io и т.п. — это резюме-/job-board, а не сайт компании.
    "potok.io",
    "huntflow.io",
    "huntflow.ru",
    "amazingjobs.ru",
    "getmatch.ru",
    "jobs.ru",
    "talantix.ru",
    "rabota.ru",
    "trudvsem.ru",
    "career.ru",
})
# NB: список держим неполным сознательно. Включаем сюда только хосты,
# которые ОБЫЧНО используются как ссылка-на-канал/профиль/пост
# («не идентифицирует одну компанию»). Если сама компания-аггрегатор
# (Telegram Inc, GitHub Inc) когда-нибудь окажется работодателем — её
# реальный domain тоже coerced в "" и dedup частично сломается; считаем
# это допустимым trade-off ради защиты от parser-pollution.


def _is_aggregator_host(host: str) -> bool:
    """True если host — агрегатор/соцсеть/мессенджер, а не корпоративный
    сайт. Suffix-match: ловит и `linkedin.com`, и `m.linkedin.com`,
    `careers.hh.ru` и т.п."""
    if not host:
        return False
    for h in _AGGREGATOR_HOSTS:
        if host == h or host.endswith("." + h):
            return True
    return False


def _signal_host(host: str) -> str:
    """Хост, очищенный от «нет сигнала о компании». Для всего, что
    является агрегатором/соцсетью/мессенджером, возвращает пустую
    строку: hard-rule по хостам тогда не вето́рит, а обращается с этим
    как с «website не указан». Альтернатива (вето́рить) ломала бы
    очевидные кейсы вроде `(Acme, acme.com)` vs `(Acme, t.me/Acme)`,
    где парсер сунул в company_website ссылку на канал — на самом деле
    это та же компания, и решение должно приниматься по name-match."""
    if not host or _is_aggregator_host(host):
        return ""
    return host


def _real_corporate_website(url: str | None) -> str | None:
    """Возвращает очищенный URL ТОЛЬКО если это настоящий корпоративный
    домен. Для aggregator/соцсеть/мессенджер ссылок (t.me/Acme,
    linkedin.com/Acme, hh.ru/employer/...) вернёт None — такие URL'ы
    не должны попадать в `company.website`, иначе UI показал бы юзеру
    ссылку-на-канал как «официальный сайт компании», а будущие парсы
    ничего полезного из этого host'а извлечь не смогут.
    Используется как enrichment-гейт И как фильтр при создании новой
    строки — оба пути иначе персистили бы aggregator-URL'ы."""
    cleaned = (url or "").strip() or None
    if not cleaned:
        return None
    if not _signal_host(_normalize_host(cleaned)):
        return None
    return cleaned


def _hosts_compatible(a: str, b: str) -> bool:
    """Hard-rule: разные непустые хосты = разные компании. Если один
    хост пустой (компания без указанного сайта) — не блокируем match."""
    if not a or not b:
        return True
    return a == b


def _enrich_company_with_parsed(
    company: Company,
    parsed_name: str,
    parsed_website: str | None,
) -> None:
    """Подсасываем parsed-данные в существующую строку:
    1. website — если в БД пусто и у нас приехал НАСТОЯЩИЙ корпоративный
       домен (не aggregator-URL: aggregator пропускаем через
       `_real_corporate_website`, чтобы не оседали как «официальный сайт
       компании» — это и неверная семантика для UI, и испорченный сигнал
       для будущих host-match'ей).
    2. parsed_name — добавляем в aliases, если такого написания ещё не
       было (ни в name, ни в существующих aliases).
    Не трогает decision/log — это чистая мутация модели, чтобы её можно
    было переиспользовать и из match-веток, и из race-fallback пути.
    """
    real_website = _real_corporate_website(parsed_website)
    if real_website and not company.website:
        company.website = real_website

    parsed_norm = _normalize_company_name(parsed_name)
    if parsed_norm:
        existing_norms = {_normalize_company_name(company.name)}
        existing_norms.update(
            _normalize_company_name(a) for a in (company.aliases or [])
        )
        if parsed_norm not in existing_norms:
            aliases = list(company.aliases or [])
            aliases.append(parsed_name.strip())
            company.aliases = aliases


def _accept_company_match(
    company: Company,
    parsed_name: str,
    parsed_website: str | None,
    decision: dict,
    stage: str,
) -> tuple[Company, dict]:
    """Использует существующую строку: enrich + decision.stage/matched_id."""
    _enrich_company_with_parsed(company, parsed_name, parsed_website)
    decision["stage"] = stage
    decision["matched_id"] = company.id
    # Аудит-лог: каждое склеивание необратимо на уровне vacancy.company_id.
    # Логируем явно, чтобы post-hoc grep по `company_dedup` показал, как
    # пайплайн пришёл к решению. Лог-host — raw-нормализованный (не
    # signal-coerced), чтобы видеть в логе исходный URL вакансии.
    logger.info(
        "company_dedup: matched stage=%s id=%d parsed_name=%r parsed_host=%r company_name=%r",
        stage,
        company.id,
        parsed_name,
        _normalize_host(parsed_website),
        company.name,
    )
    return company, decision


async def _create_company_row(
    session: AsyncSession,
    name: str,
    website: str | None,
    decision: dict,
) -> tuple[Company | None, dict]:
    """Создание новой строки. На race по UNIQUE(name) — re-lookup точного
    совпадения (детерминированное, без LLM, чтобы не закольцеваться) и
    обогащение найденной строки тем же enrichment'ом, что в match-ветках
    (website-fill / alias-fold) — чтобы concurrent ingest не терял
    parsed-данные.

    Если decision["stage"] уже несёт сигнал «LLM был вызван и не
    сматчил» (`llm_no_match`), сохраняем его в `pre_create_stage` ДО
    перезаписи на `create`, иначе DB-only audit не отличит «LLM пробовали»
    от «LLM не вызывался»."""
    # Aggregator-URL'ы НЕ персистим как website новой компании по тем же
    # причинам, что в _enrich_company_with_parsed: «канальная» ссылка не
    # является корпоративным сайтом. None в этой колонке честнее, чем
    # ложный t.me/AcmeChannel, и не отравляет будущий host-match.
    persisted_website = _real_corporate_website(website)
    prior_stage = decision.get("stage")
    if prior_stage and prior_stage not in ("skip", None):
        decision["pre_create_stage"] = prior_stage
    name_clean = name.strip()
    try:
        async with session.begin_nested():
            company = Company(
                name=name_clean,
                aliases=[],
                website=persisted_website,
            )
            session.add(company)
            await session.flush()
        decision["stage"] = "create"
        decision["matched_id"] = company.id
        logger.info(
            "company_dedup: created id=%d name=%r website=%r",
            company.id,
            name_clean,
            persisted_website,
        )
        return company, decision
    except IntegrityError:
        # UNIQUE(name) в SQLite case-sensitive: IntegrityError срабатывает
        # только на точное совпадение. Re-lookup делаем по той же точной
        # строке, что и пытались insert'ить — иначе case-insensitive lower()
        # мог бы вернуть row, который НЕ был причиной race-collision.
        company = (
            await session.scalars(
                select(Company).where(Company.name == name_clean)
            )
        ).first()
        if company is not None:
            # Race produced a row with same name. Применяем тот же
            # enrichment, что в match-ветках: parsed-данные не должны
            # теряться от того, что concurrent ingest нас опередил.
            _enrich_company_with_parsed(company, name, website)
            decision["stage"] = "create_race_fallback"
            decision["matched_id"] = company.id
            logger.info(
                "company_dedup: race fallback id=%d name=%r",
                company.id,
                name_clean,
            )
        return company, decision


async def find_or_create_company(
    session: AsyncSession,
    name: str,
    *,
    website: str | None = None,
    lm_client: Any = None,
    lm_model: str | None = None,
) -> tuple[Company | None, dict]:
    """Резолв распарсенной (name, website) пары к существующей компании
    или создание новой. Возвращает кортеж (company, decision).

    decision — dict с полями:
        stage:    "rule_name" | "rule_alias" | "rule_website" |
                  "llm_match" | "llm_no_match" | "create" |
                  "create_race_fallback" | "skip"
        matched_id:    int | None — id того row'а, к которому свелось
        candidates:    [{id, name, website}, ...] | None — shortlist для
                       LLM (заполняется только когда LLM вызывался)
        llm_reasoning: str | None — короткий ответ LLM

    ``lm_client`` / ``lm_model`` опциональны: без них Stage 2 пропускается,
    схема вырождается в чистые правила + create. Это удобно для тестов и
    для путей, где LLM-вызов нежелателен.
    """
    decision: dict = {
        "stage": "skip",
        "matched_id": None,
        "candidates": None,
        "llm_reasoning": None,
    }
    raw_name = (name or "").strip()
    if not raw_name:
        return None, decision

    parsed_norm = _normalize_company_name(raw_name)
    # Hard-rule по host'ам должен опираться только на «настоящие» сигналы:
    # агрегаторы (t.me, linkedin, hh.ru…) обращаемся как с пустым host'ом —
    # иначе попавшая в company_website ссылка на канал/профиль ломала бы
    # name-match для одной и той же компании. Coerce делаем здесь, дальше
    # везде используем уже очищенный host.
    parsed_host = _signal_host(_normalize_host(website))

    rows = list((await session.scalars(select(Company))).all())
    # Pre-вычисляем нормализованные представления каждой компании, чтобы не
    # повторять normalize в трёх внутренних циклах. c_host тоже сразу
    # пропускаем через _signal_host — для legacy-данных, где в БД могла
    # лечь ссылка на t.me как website.
    norms: list[tuple[Company, str, list[str], str]] = []
    for c in rows:
        norms.append(
            (
                c,
                _normalize_company_name(c.name),
                [_normalize_company_name(a) for a in (c.aliases or [])],
                _signal_host(_normalize_host(c.website)),
            )
        )

    # Если нормализация ужала имя в пустую строку — это значит на входе
    # пришёл только legal-suffix (например, "SAS"/"LLC"/"ПАО") без бренд-
    # ядра, либо имя из символов, которые мы выкинули как пунктуацию. Не
    # пускаем в name/alias-match: пустая строка совпала бы с любой другой
    # такой же пустой и склеила бы заведомо разные «голые» юр.формы.
    # Хост-match (Stage 1c) работает дальше как обычно — это безопаснее.
    if parsed_norm:
        # Stage 1a — точное совпадение нормализованного имени.
        # NB: ловит только варианты одного и того же написания (МТС/MTС/MTS
        # после транслитерации, ПАО Сбербанк → Сбербанк после strip'а суффикса).
        # «Бренд vs полное юр.название» (Сбер vs Сбербанк) сюда не
        # попадает — норм-формы у них разные ("sber" vs "sberbank") — это
        # территория Stage 2 (LLM-арбитр).
        for c, c_name_norm, _aliases, c_host in norms:
            if (
                c_name_norm
                and c_name_norm == parsed_norm
                and _hosts_compatible(c_host, parsed_host)
            ):
                return _accept_company_match(
                    c, raw_name, website, decision, "rule_name"
                )

        # Stage 1b — алиас совпал.
        for c, _name, c_aliases, c_host in norms:
            if any(
                a and a == parsed_norm for a in c_aliases
            ) and _hosts_compatible(c_host, parsed_host):
                return _accept_company_match(
                    c, raw_name, website, decision, "rule_alias"
                )

    # Stage 1c — точный match по хосту. Агрегаторы уже скоэрсены в "" в
    # _signal_host, поэтому если parsed_host здесь непустой — это реальный
    # corporate-домен. То же по c_host у каждого row.
    #
    # Намеренная асимметрия с user-rule «одинаковое имя + разные сайты =
    # разные компании»: ОБРАТНЫЙ кейс — «разные имена + одинаковый сайт» —
    # здесь склеивается без обращения к LLM. Логика: corporate-домен —
    # это сильный сигнал (rebrand / brand-vs-legal-name / parser-вариация
    # на одной и той же странице). Если в будущем выяснится, что и этот
    # путь даёт false-positives, можно ввести Левенштейн-порог по имени и
    # роутить low-similarity случаи через Stage 2.
    if parsed_host:
        for c, _name, _aliases, c_host in norms:
            if c_host and c_host == parsed_host:
                return _accept_company_match(
                    c, raw_name, website, decision, "rule_website"
                )

    # Stage 2 — LLM-арбитр. Кандидатами идут только те, кто прошёл по
    # similarity И не нарушает hard-rule по хостам. Иначе LLM не вызываем.
    # При пустом parsed_norm (имя свелось к пустоте после нормализации)
    # SequenceMatcher вернул бы 1.0 на любую другую пустую — и склеил бы
    # «голые» legal-suffix-имена. Skip'аем Stage 2, идём в create.
    if parsed_norm and lm_client is not None and lm_model:
        candidates: list[tuple[Company, float]] = []
        for c, c_name_norm, c_aliases, c_host in norms:
            if not _hosts_compatible(c_host, parsed_host):
                continue
            ratio_name = (
                SequenceMatcher(None, parsed_norm, c_name_norm).ratio()
                if c_name_norm
                else 0.0
            )
            ratio_alias = max(
                (
                    SequenceMatcher(None, parsed_norm, a).ratio()
                    for a in c_aliases
                    if a
                ),
                default=0.0,
            )
            best = max(ratio_name, ratio_alias)
            if best >= 0.7:
                candidates.append((c, best))
        candidates.sort(key=lambda x: -x[1])
        candidates = candidates[:5]
        if candidates:
            # Lazy import: repo не должен жёстко зависеть от llm-модуля при
            # импорте; LLM нужен только в этой ветке.
            from backend.llm import dedupe_company_with_llm

            shortlist = [c for c, _ in candidates]
            matched_id, reasoning = await dedupe_company_with_llm(
                lm_client,
                lm_model,
                parsed_name=raw_name,
                parsed_website=website,
                candidates=shortlist,
            )
            decision["candidates"] = [
                {"id": c.id, "name": c.name, "website": c.website}
                for c in shortlist
            ]
            decision["llm_reasoning"] = reasoning
            if matched_id is not None:
                # Hallucination-guard: LLM может вернуть id, которого мы
                # ему не давали. Принимаем только то, что было в shortlist.
                match = next(
                    (c for c in shortlist if c.id == matched_id), None
                )
                if match is not None:
                    return _accept_company_match(
                        match, raw_name, website, decision, "llm_match"
                    )
                # Galлюцинация: LLM ответил id'шник, которого мы ему не
                # давали. Сохраняем его в decision для post-hoc grep'а —
                # иначе следы только в reasoning-тексте, нечитаемо.
                decision["llm_hallucinated_id"] = matched_id
                logger.warning(
                    "company_dedup: LLM hallucinated id=%r outside shortlist=%r",
                    matched_id,
                    [c.id for c in shortlist],
                )
            decision["stage"] = "llm_no_match"
            # Аудит-лог: LLM был вызван, но решил «не то». Без отдельной
            # записи следующий logger.info("created ...") выглядит так,
            # будто LLM не вызывался вовсе. parsed_host логируем raw-
            # нормализованный (не signal-coerced) — чтобы видеть, какой
            # URL пришёл из вакансии, а не пустую строку после coercion.
            logger.info(
                "company_dedup: llm_no_match parsed_name=%r parsed_host=%r "
                "shortlist_ids=%r reasoning=%r",
                raw_name,
                _normalize_host(website),
                [c.id for c in shortlist],
                reasoning,
            )

    # Stage 3 — создаём новую.
    return await _create_company_row(session, raw_name, website, decision)


async def merge_company(
    session: AsyncSession, *, absorbed_id: int, survivor_id: int
) -> None:
    """Merge ``absorbed`` company into ``survivor``. Irreversible.

    Caller must wrap in ``session.begin()``.
    """
    if absorbed_id == survivor_id:
        raise ValueError("merge_company: absorbed_id == survivor_id")
    absorbed = await session.get(Company, absorbed_id)
    survivor = await session.get(Company, survivor_id)
    if absorbed is None or survivor is None:
        raise ValueError(
            f"merge_company: not found "
            f"(absorbed={absorbed_id}, survivor={survivor_id})"
        )

    abs_name = absorbed.name
    abs_aliases = list(absorbed.aliases or [])
    abs_website = absorbed.website
    abs_notes = absorbed.notes

    moved_vacancies = (
        await session.execute(
            update(Vacancy)
            .where(Vacancy.company_id == absorbed_id)
            .values(company_id=survivor_id)
        )
    ).rowcount or 0

    await session.delete(absorbed)
    await session.flush()

    aliases = list(survivor.aliases or [])
    seen = {a.casefold() for a in aliases}
    for candidate in abs_aliases + [abs_name]:
        if candidate and candidate.casefold() not in seen:
            aliases.append(candidate)
            seen.add(candidate.casefold())
    survivor.aliases = aliases

    if not survivor.website and abs_website:
        survivor.website = abs_website
    survivor.notes = _concat_notes(survivor.notes, abs_notes)

    logger.info(
        "merged company #%d -> #%d (vacancies=%d)",
        absorbed_id, survivor_id, moved_vacancies,
    )


async def delete_hr(session: AsyncSession, hr_id: int) -> bool:
    """Cascade-delete the HR row. Caller commits.

    Messages are removed (chat history is meaningless without the HR);
    vacancies survive with ``hr_id`` set to NULL — they're intrinsic to
    their source channel, not to who messaged us about them. Returns
    ``True`` if the HR existed and was removed, ``False`` if not found.
    """
    hr = await session.get(HR, hr_id)
    if hr is None:
        return False
    hr_label = hr.name or hr.telegram_username
    msgs_deleted = (
        await session.execute(delete(Message).where(Message.hr_id == hr_id))
    ).rowcount
    detached = (
        await session.execute(
            update(Vacancy).where(Vacancy.hr_id == hr_id).values(hr_id=None)
        )
    ).rowcount
    await session.delete(hr)
    logger.info(
        "Deleted HR %d (%r), messages purged=%d, vacancies detached=%d",
        hr_id,
        hr_label,
        int(msgs_deleted or 0),
        int(detached or 0),
    )
    return True


def hr_blacklist_preferred_value(hr: HR) -> str | None:
    """The single value the «Add to blacklist» action should write.

    Prefers @username (human-readable on the Blacklist screen); falls
    back to user_id when no username is set.
    """
    if hr.telegram_username:
        return f"@{hr.telegram_username}"
    if hr.telegram_user_id is not None:
        return f"user_id:{hr.telegram_user_id}"
    return None


async def merge_hr(
    session: AsyncSession, *, absorbed_id: int, survivor_id: int
) -> None:
    """Merge ``absorbed`` HR into ``survivor``. Irreversible.

    Caller must wrap in ``session.begin()``.

    Semantics:
    * Vacancies are unioned (absorbed's get repointed onto survivor).
    * **TG account + chat history travel together as one unit.** If
      survivor has a ``telegram_user_id`` → keep its TG identity + chat,
      DROP absorbed's chat (and its TG identity is discarded with it). If
      survivor has no ``telegram_user_id`` → take absorbed's
      ``telegram_user_id`` + ``telegram_username`` AND move its chat onto
      survivor. Username alone doesn't count as an account — without a
      user_id it's just a manual hint.
    * Name falls back from absorbed only when survivor's is empty.
    * Notes are concatenated so nothing is silently lost.
    """
    if absorbed_id == survivor_id:
        raise ValueError("merge_hr: absorbed_id == survivor_id")
    absorbed = await session.get(HR, absorbed_id)
    survivor = await session.get(HR, survivor_id)
    if absorbed is None or survivor is None:
        raise ValueError(
            f"merge_hr: not found "
            f"(absorbed={absorbed_id}, survivor={survivor_id})"
        )

    abs_tg_user_id = absorbed.telegram_user_id
    abs_tg_username = absorbed.telegram_username
    abs_name = absorbed.name
    abs_notes = absorbed.notes
    survivor_has_tg = survivor.telegram_user_id is not None

    moved_vacancies = (
        await session.execute(
            update(Vacancy)
            .where(Vacancy.hr_id == absorbed_id)
            .values(hr_id=survivor_id)
        )
    ).rowcount or 0
    if survivor_has_tg:
        dropped_messages = (
            await session.execute(
                delete(Message).where(Message.hr_id == absorbed_id)
            )
        ).rowcount or 0
        moved_messages = 0
    else:
        moved_messages = (
            await session.execute(
                update(Message)
                .where(Message.hr_id == absorbed_id)
                .values(hr_id=survivor_id)
            )
        ).rowcount or 0
        dropped_messages = 0

    await session.delete(absorbed)
    await session.flush()

    if not survivor_has_tg:
        # TG identity travels with the chat — only adopt absorbed's tg
        # when survivor didn't have an account of its own.
        if abs_tg_user_id is not None:
            survivor.telegram_user_id = abs_tg_user_id
        if abs_tg_username:
            survivor.telegram_username = abs_tg_username
    if not survivor.name and abs_name:
        survivor.name = abs_name
    survivor.notes = _concat_notes(survivor.notes, abs_notes)

    logger.info(
        "merged HR #%d -> #%d (vacancies=%d, messages moved=%d, dropped=%d)",
        absorbed_id, survivor_id, moved_vacancies, moved_messages, dropped_messages,
    )


def _concat_notes(survivor: str | None, absorbed: str | None) -> str | None:
    parts = [p.strip() for p in (survivor, absorbed) if p and p.strip()]
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0]
    return "\n---\n".join(parts)


async def find_or_create_hr(
    session: AsyncSession, user, *, avatar: bytes | None = None
) -> tuple[HR, bool]:
    """Return (hr, created). ``created=True`` ⇒ row только что вставлен —
    caller (vacancy parse path: основная ветка с автоотправкой и NotFit-
    save) использует это, чтобы запустить per-HR backfill DM-истории.
    Catch-up для всех HR'ов крутится только на OFF→active transition;
    новый HR, созданный в активном режиме, без этого хука остался бы с
    пустым чатом до рестарта."""
    hr = (
        await session.scalars(
            select(HR).where(HR.telegram_user_id == user.id)
        )
    ).first()
    if hr is None and user.username:
        hr = (
            await session.scalars(
                select(HR).where(
                    HR.telegram_username == user.username,
                    HR.telegram_user_id.is_(None),
                )
            )
        ).first()

    full_name = " ".join(
        filter(None, [user.first_name, user.last_name])
    ).strip() or None

    if hr is None:
        hr = HR(
            telegram_user_id=user.id,
            telegram_username=user.username,
            name=full_name,
            avatar=avatar,
        )
        session.add(hr)
        await session.flush()
        logger.info(
            "Created HR id=%d telegram_user_id=%s username=%s name=%r",
            hr.id,
            user.id,
            user.username,
            full_name,
        )
        return hr, True

    if hr.telegram_user_id is None:
        hr.telegram_user_id = user.id
    if user.username and hr.telegram_username != user.username:
        hr.telegram_username = user.username
    if not hr.name and full_name:
        hr.name = full_name
    # Backfill only when empty — keeps a freshly-fetched photo from being
    # overwritten by a stale fetch on a later flow. Trade-off: if the HR
    # changes their Telegram photo, the bot keeps the old one until the
    # column is manually cleared.
    if avatar is not None and hr.avatar is None:
        hr.avatar = avatar
    return hr, False


async def load_profile_skills(session: AsyncSession) -> list[ProfileSkill]:
    return list(
        (await session.scalars(select(ProfileSkill))).all()
    )


_SKILL_KEY_RE = re.compile(r"[\s\-_./]+")


def _normalize_skill_key(s: str) -> str:
    """Lower-cased, whitespace-/punctuation-collapsed key for skill matching.

    Lets ``stack: ["Postgres"]`` find a ProfileSkill named "PostgreSQL" with
    alias "Postgres", and tolerates "Docker-Compose" vs "docker compose".
    """
    return _SKILL_KEY_RE.sub(" ", s.strip().lower()).strip()


async def save_parsed_cv(
    session: AsyncSession, parsed: ParsedCv, *, cv_path: str | None = None
) -> None:
    """Replace the single Profile (and its skills/experience) with parsed data.

    If ``cv_path`` is provided, also upserts ``app_settings.cv_path`` in the
    same transaction so the wizard's "parse-and-save" step is atomic
    (otherwise a crash between the two writes leaves a parsed profile with
    no recorded source file).

    Caller must wrap in ``session.begin()``. Wipes existing rows because the
    wizard implies a fresh write — partial merging would cause stale skills
    to silently linger.
    """
    await session.execute(delete(profile_experience_skills))
    await session.execute(delete(ProfileExperience))
    await session.execute(delete(ProfileSkill))
    await session.execute(delete(ProfileLanguage))
    await session.execute(delete(Profile))
    await session.flush()

    p = parsed.profile
    profile = Profile(
        first_name=p.first_name,
        last_name=p.last_name,
        title=p.title,
        email=p.email,
        phone=p.phone,
        location=p.location,
        telegram_username=p.telegram_username,
        github_url=p.github_url,
        education=p.education,
        work_format=list(p.work_format),
        grades=list(p.grades),
        free_preferences=p.free_preferences,
    )
    session.add(profile)
    await session.flush()

    for lang in parsed.languages:
        session.add(
            ProfileLanguage(
                profile_id=profile.id,
                language=lang.language,
                level=lang.level,
            )
        )
    await session.flush()

    skill_lookup: dict[str, ProfileSkill] = {}
    for s in parsed.skills:
        row = ProfileSkill(
            profile_id=profile.id,
            category=s.category,
            name=s.name,
            level=s.level,
            aliases=list(s.aliases),
        )
        session.add(row)
        for key_src in (s.name, *s.aliases):
            key = _normalize_skill_key(key_src)
            if not key:
                continue
            existing = skill_lookup.get(key)
            if existing is not None and existing is not row:
                logger.warning(
                    "save_parsed_cv: skill key %r collides between %r and %r, keeping first",
                    key, existing.name, row.name,
                )
                continue
            skill_lookup[key] = row
    await session.flush()

    for e in parsed.experience:
        exp = ProfileExperience(
            profile_id=profile.id,
            company=e.company,
            company_url=e.company_url,
            role=e.role,
            start_date=e.start_date,
            end_date=e.end_date,
            achievements=list(e.achievements),
            responsibilities=list(e.responsibilities),
        )
        for tech in e.stack:
            key = _normalize_skill_key(tech)
            row = skill_lookup.get(key) if key else None
            if row is not None:
                exp.skills.append(row)
            else:
                logger.warning(
                    "save_parsed_cv: experience %r stack item %r not matched to any ProfileSkill",
                    e.company, tech,
                )
        session.add(exp)
    await session.flush()

    if cv_path is not None:
        existing = await session.get(AppSetting, "cv_path")
        if existing is None:
            session.add(AppSetting(key="cv_path", value=cv_path))
        else:
            existing.value = cv_path
        await session.flush()

    logger.info(
        "Profile replaced: languages=%d skills=%d experiences=%d cv_path=%s",
        len(parsed.languages),
        len(parsed.skills),
        len(parsed.experience),
        cv_path,
    )


async def list_skills(session: AsyncSession) -> list[ProfileSkill]:
    """All ProfileSkill rows ordered by id (preserves user-set order)."""
    return list(
        (await session.scalars(select(ProfileSkill).order_by(ProfileSkill.id))).all()
    )


async def list_experience(session: AsyncSession) -> list[ProfileExperience]:
    """All ProfileExperience rows newest-first, with skills relationship loaded."""
    from sqlalchemy.orm import selectinload

    return list(
        (
            await session.scalars(
                select(ProfileExperience)
                .options(selectinload(ProfileExperience.skills))
                .order_by(ProfileExperience.start_date.desc())
            )
        ).all()
    )


async def save_skills(
    session: AsyncSession,
    rows: list[dict],
    profile_id: int,
) -> None:
    """Update / insert / delete skills by id, preserving experience links.

    Each row may carry an integer ``id`` (existing row → UPDATE) or a None
    / string id (new row → INSERT). Rows whose ids are not present in the
    payload get DELETEd along with their junction entries. UPDATEing a row
    leaves its row id stable, so profile_experience_skills naturally
    survives even if the user renamed the skill.

    Caller wraps in ``session.begin()``.
    """
    existing = {s.id: s for s in await list_skills(session)}
    keep_ids: set[int] = set()

    for row in rows:
        name = (row.get("name") or "").strip()
        if not name:
            continue
        category = (row.get("category") or "Общее").strip() or "Общее"
        try:
            level = int(row.get("level") or 1)
        except (TypeError, ValueError):
            level = 1
        aliases = [
            a for a in (row.get("aliases") or [])
            if isinstance(a, str) and a.strip()
        ]
        rid = row.get("id")
        rid_int = rid if isinstance(rid, int) else None

        if rid_int is not None and rid_int in existing:
            s = existing[rid_int]
            s.category = category
            s.name = name
            s.level = level
            s.aliases = aliases
            keep_ids.add(rid_int)
        else:
            session.add(ProfileSkill(
                profile_id=profile_id,
                category=category,
                name=name,
                level=level,
                aliases=aliases,
            ))

    # Delete rows the user removed. Junction has no ON DELETE CASCADE on
    # SQLite by default, so wipe the links explicitly first.
    drop_ids = set(existing.keys()) - keep_ids
    for sid in drop_ids:
        await session.execute(
            delete(profile_experience_skills).where(
                profile_experience_skills.c.skill_id == sid
            )
        )
        await session.delete(existing[sid])
    await session.flush()
    logger.debug(
        "Saved skills: kept=%d dropped=%d", len(keep_ids), len(drop_ids)
    )


class SaveExperienceError(ValueError):
    """Raised on validation failure during save_experience.

    Attribute ``index`` is the 1-based row number that failed; ``problem``
    describes what's wrong in human-readable Russian for the UI.
    """

    def __init__(self, index: int, problem: str) -> None:
        self.index = index
        self.problem = problem
        super().__init__(f"Запись #{index}: {problem}")


async def save_experience(
    session: AsyncSession,
    rows: list[dict],
    profile_id: int,
) -> None:
    """Replace all ProfileExperience rows + their skill links.

    Validates eagerly: on the first invalid row the call raises
    ``SaveExperienceError`` BEFORE any DB writes, so the caller can show a
    targeted error and the user doesn't lose data they typed. Skills are
    matched to existing ProfileSkill rows by name; unknown names are
    dropped silently (UI's skill picker only offers existing skills).

    Caller wraps in ``session.begin()``.
    """
    skills_by_name: dict[str, ProfileSkill] = {
        s.name.lower(): s for s in await list_skills(session)
    }

    # Validate everything first — fail fast, no half-applied state.
    parsed_rows: list[tuple[dict, date, date | None]] = []
    for i, row in enumerate(rows, start=1):
        company = (row.get("company") or "").strip()
        role = (row.get("role") or "").strip()
        start_iso = (row.get("start_date") or "").strip()
        if not company:
            raise SaveExperienceError(i, "не заполнено название компании")
        if not role:
            raise SaveExperienceError(i, "не заполнена должность")
        if not start_iso:
            raise SaveExperienceError(i, "не заполнена дата начала")
        try:
            start_date = date.fromisoformat(start_iso)
        except ValueError:
            raise SaveExperienceError(i, f"неверная дата начала: {start_iso!r}")
        end_iso = (row.get("end_date") or "").strip()
        end_date: date | None = None
        if end_iso:
            try:
                end_date = date.fromisoformat(end_iso)
            except ValueError:
                raise SaveExperienceError(
                    i, f"неверная дата окончания: {end_iso!r}"
                )
        parsed_rows.append((row, start_date, end_date))

    await session.execute(delete(profile_experience_skills))
    await session.execute(delete(ProfileExperience))
    await session.flush()

    for row, start_date, end_date in parsed_rows:
        company_url = (row.get("company_url") or "").strip() or None
        exp = ProfileExperience(
            profile_id=profile_id,
            company=row["company"].strip(),
            company_url=company_url,
            role=row["role"].strip(),
            start_date=start_date,
            end_date=end_date,
            achievements=[
                a for a in (row.get("achievements") or []) if isinstance(a, str) and a.strip()
            ],
            responsibilities=[
                r for r in (row.get("responsibilities") or []) if isinstance(r, str) and r.strip()
            ],
        )
        for sname in (row.get("skill_names") or []):
            s = skills_by_name.get(str(sname).lower())
            if s is not None:
                exp.skills.append(s)
        session.add(exp)
    await session.flush()
    logger.debug("Saved experiences: %d rows", len(parsed_rows))


async def get_profile(session: AsyncSession) -> Profile | None:
    """Return the single Profile row, if any."""
    return (await session.scalars(select(Profile).limit(1))).first()


async def upsert_profile(session: AsyncSession, **fields) -> Profile:
    """Update the single Profile row's basic fields, or create it.

    Caller must wrap in ``session.begin()``. Skills and experience are NOT
    touched here — those have their own write paths.
    """
    profile = (await session.scalars(select(Profile).limit(1))).first()
    if profile is None:
        profile = Profile(**fields)
        session.add(profile)
    else:
        for key, value in fields.items():
            setattr(profile, key, value)
    await session.flush()
    logger.debug("Profile upserted (fields=%s)", list(fields.keys()))
    return profile


async def list_profile_languages(
    session: AsyncSession,
) -> list[ProfileLanguage]:
    """Return all profile_language rows ordered by id (insertion order)."""
    rows = await session.scalars(
        select(ProfileLanguage).order_by(ProfileLanguage.id)
    )
    return list(rows)


async def replace_profile_languages(
    session: AsyncSession,
    profile_id: int,
    items: list[tuple[str, str]],
) -> None:
    """Wipe and re-insert profile_language rows for ``profile_id``.

    Caller must wrap in ``session.begin()``. The table is small (1-5 rows
    per profile), so a full replace is simpler than diff-and-update and
    keeps the (profile_id, language) uniqueness invariant trivially true.
    """
    await session.execute(
        delete(ProfileLanguage).where(
            ProfileLanguage.profile_id == profile_id
        )
    )
    await session.flush()
    for language, level in items:
        session.add(
            ProfileLanguage(
                profile_id=profile_id, language=language, level=level
            )
        )
    await session.flush()
    logger.debug("Profile languages replaced (count=%d)", len(items))


async def list_hrs_with_unread(session: AsyncSession) -> list[dict]:
    """HRs that have at least one unread incoming message — for the footer
    pop-up. Ordered by most recent unread first so the latest noise is on
    top. Returns plain dicts; the bridge serialises them as-is.
    """
    rows = (
        await session.execute(
            select(
                HR.id,
                HR.name,
                HR.telegram_username,
                func.count(Message.id).label("unread"),
                func.max(Message.sent_at).label("last_at"),
            )
            .join(Message, Message.hr_id == HR.id)
            .where(
                Message.is_incoming,
                Message.read_at.is_(None),
                Message.is_deleted.is_(False),
            )
            .group_by(HR.id)
            .order_by(func.max(Message.sent_at).desc())
        )
    ).all()
    return [
        {
            "hr_id": int(hr_id),
            "name": name,
            "telegram_username": tg_username,
            "unread_count": int(unread or 0),
            "last_at": last_at.isoformat() if last_at else None,
        }
        for hr_id, name, tg_username, unread, last_at in rows
    ]


async def count_unread_incoming(session: AsyncSession) -> int:
    """Count incoming HR messages whose read_at is still NULL.

    Excludes tombstones — a deleted incoming row that was never read
    would otherwise inflate the badge with no way to clear it from the UI.
    ``_on_dm_delete`` also seals ``read_at`` defensively, but the filter
    here protects against any future code that flips ``is_deleted`` only.
    """
    n = await session.scalar(
        select(func.count(Message.id)).where(
            Message.is_incoming,
            Message.read_at.is_(None),
            Message.is_deleted.is_(False),
        )
    )
    return int(n or 0)


async def load_active_blacklist_patterns(
    session: AsyncSession,
) -> list[str]:
    return list(
        (
            await session.scalars(
                select(Blacklist.value).where(Blacklist.active)
            )
        ).all()
    )



async def build_profile_block(session: AsyncSession) -> str:
    """Текстовый блок «Информация о кандидате» для cover-letter промпта.

    Собирает имя/роль/локацию/годы опыта (вычисляются по самой ранней
    ProfileExperience), скиллы по категориям и список мест работы. Если
    ``Profile.free_preferences`` заполнен — добавляется отдельной секцией
    «Дополнительно», чтобы LLM могла учесть пожелания (про релокацию, гео,
    специфичные предпочтения).
    """
    profile = (await session.scalars(select(Profile).limit(1))).first()
    if profile is None:
        return ""

    skills = list(
        (await session.scalars(select(ProfileSkill).order_by(ProfileSkill.id))).all()
    )
    experiences = list(
        (
            await session.scalars(
                select(ProfileExperience).order_by(ProfileExperience.start_date.desc())
            )
        ).all()
    )

    skills_by_cat: dict[str, list[str]] = {}
    for s in skills:
        skills_by_cat.setdefault(s.category, []).append(s.name)
    skills_lines = [f"- {cat}: {', '.join(names)}" for cat, names in skills_by_cat.items()]

    # Незаполненные поля (None в БД) пропускаем целиком, иначе LLM получит
    # «Имя: None None» / «Роль: None» и попытается включить это в письмо.
    full_name = " ".join(
        p for p in (profile.first_name, profile.last_name) if p
    ).strip()
    header_lines: list[str] = []
    if full_name:
        header_lines.append(f"Имя: {full_name}")
    if profile.title:
        header_lines.append(f"Роль: {profile.title}")
    if profile.location:
        header_lines.append(f"Локация: {profile.location}")
    if experiences:
        min_start = min(e.start_date for e in experiences)
        today = date.today()
        years = today.year - min_start.year - (
            (today.month, today.day) < (min_start.month, min_start.day)
        )
        years = max(years, 0)
        header_lines.append(f"Опыт: {years}+ лет в IT")

    exp_lines = []
    for e in experiences:
        end = e.end_date.strftime("%m.%Y") if e.end_date else "настоящее время"
        start = e.start_date.strftime("%m.%Y")
        suffix = f": {e.achievements[0]}" if e.achievements else ""
        exp_lines.append(f"- {e.company} ({e.role}, {start} — {end}){suffix}")

    sections: list[str] = []
    if header_lines:
        sections.append("\n".join(header_lines))
    if skills_lines:
        sections.append("Стек:\n" + "\n".join(skills_lines))
    if exp_lines:
        sections.append("Опыт работы:\n" + "\n".join(exp_lines))
    if profile.free_preferences:
        sections.append("Дополнительно:\n" + profile.free_preferences.strip())
    return "\n\n".join(sections)
