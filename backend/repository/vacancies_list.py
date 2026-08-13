"""Отбор вакансий для списка на экране."""

from datetime import datetime

from sqlalchemy import String, case, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.spellings import dedupe_first_wins
from backend.models import (
    Company,
    HR,
    TelegramChannel,
    Vacancy,
    VacancyEvent,
    VacancyStatus,
    VacancyStatusHistory,
)
from backend.payloads import VacancyFilter
from backend.repository.paging import trim_page
from backend.repository.vacancies_card import VACANCY_NEIGHBOURS
from backend.repository.vacancies_common import PARSED_ONLY

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


def _activity_aggs(ids: list[int] | None = None):
    """Свежайшее событие и свежайшая смена статуса — по одной строке на вакансию.

    Названные номера сужают обе группировки: спрашивая метку для полусотни
    показанных строк, незачем группировать всю ленту событий. Список так
    сузить нельзя — он отбирает уже после соединения, — поэтому довод
    необязательный.
    """
    event_q = select(
        VacancyEvent.vacancy_id.label("vid"),
        func.max(VacancyEvent.created_at).label("max_at"),
    )
    status_q = select(
        VacancyStatusHistory.vacancy_id.label("vid"),
        func.max(VacancyStatusHistory.changed_at).label("max_at"),
    )
    if ids is not None:
        event_q = event_q.where(VacancyEvent.vacancy_id.in_(ids))
        status_q = status_q.where(VacancyStatusHistory.vacancy_id.in_(ids))
    return (
        event_q.group_by(VacancyEvent.vacancy_id).subquery("event_agg"),
        status_q.group_by(VacancyStatusHistory.vacancy_id).subquery("status_agg"),
    )


def _activity_ts(event_agg, status_agg):
    """Метка активности вакансии — позднейшее из четырёх времён.

    Перечень источников один на обе дороги: по нему список сортирует прямо в
    запросе, по нему же окно спрашивает метку для показанных строк. Написанный
    порознь, он разошёлся бы молча — вакансия стояла бы первой, показывая дату
    второй.
    """
    return _greatest(
        Vacancy.created_at,
        Vacancy.posted_at,
        event_agg.c.max_at,
        status_agg.c.max_at,
    )


def _order_for(sort: str, activity_ts):
    """Порядок выдачи по ключу сортировки; незнакомый ключ — «сначала свежие».

    Номер строки идёт последним у каждого ключа: у меток активности бывают
    совпадения, и без него порядок двух таких строк решался бы случаем — от
    страницы к странице они менялись бы местами.

    Незнакомый ключ отсекается здесь, а не у зовущего: перечень известных
    и разбор по ним — одно знание, и порознь они разъехались бы.
    """
    if sort not in VACANCY_SORTS:
        return (activity_ts.desc().nulls_last(), Vacancy.id.desc())
    if sort == "oldest":
        return (activity_ts.asc().nulls_last(), Vacancy.id.asc())
    if sort == "score_desc":
        return (
            Vacancy.score.desc().nulls_last(),
            activity_ts.desc(),
            Vacancy.id.desc(),
        )
    if sort == "score_asc":
        return (
            Vacancy.score.asc().nulls_last(),
            activity_ts.desc(),
            Vacancy.id.desc(),
        )
    if sort in ("status_active_first", "status_new_first"):
        ranks = (
            _STATUS_PRIORITY_ACTIVE_FIRST
            if sort == "status_active_first"
            else _STATUS_PRIORITY_NEW_FIRST
        )
        priority = case(
            *[(Vacancy.status == s, p) for s, p in ranks.items()], else_=999
        )
        return (priority.asc(), activity_ts.desc(), Vacancy.id.desc())
    return (activity_ts.desc().nulls_last(), Vacancy.id.desc())


def _search_clauses(search: str | None) -> tuple[list, set[str]]:
    """Условие поиска подстрокой и соседи, которых оно требует.

    Ищется по девяти колонкам и по сырому JSON стека — по всему, что человек
    видит в строке списка. Имя HR и имя компании лежат в своих таблицах,
    поэтому соседи называются здесь же: знание «какое условие без какого
    соседа не читается» живёт при самом условии, а не у зовущего.
    """
    if not search or not search.strip():
        return [], set()
    q = f"%{search.strip().lower()}%"
    matched = or_(
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
    return [matched], {"hr", "company"}


def _choice_clauses(f: VacancyFilter) -> tuple[list, set[str]]:
    """Условия по спискам выбранного в окне и соседи, которых они требуют.

    Регистр сводится потому, что его сводит и выпадающий список (см.
    :func:`list_vacancy_filter_options`): из «Контур» и «контур» он оставляет
    первое встреченное написание, второго не предлагает вовсе, и точное
    сравнение оставило бы вакансию со вторым написанием недостижимой через
    фильтр. `lower` здесь свой, зарегистрированный в `adapters/db.py`, и
    кириллицу он понимает.
    """
    clauses: list = []
    joins: set[str] = set()
    if f.statuses:
        enum_values = [_STATUS_BY_CODE[s] for s in f.statuses if s in _STATUS_BY_CODE]
        if enum_values:
            clauses.append(Vacancy.status.in_(enum_values))
    if f.channels:
        cleaned = [c.lower() for c in f.channels if c]
        if cleaned:
            clauses.append(func.lower(TelegramChannel.username).in_(cleaned))
            joins.add("channel")
    if f.companies:
        cleaned = [c.lower() for c in f.companies if c]
        if cleaned:
            clauses.append(
                or_(
                    func.lower(Company.name).in_(cleaned),
                    func.lower(Vacancy.company_name).in_(cleaned),
                )
            )
            joins.add("company")
    return clauses, joins


def _range_clauses(f: VacancyFilter, activity_ts) -> list:
    """Условия по числовым и временным границам.

    Окно зарплаты и вилка вакансии сравниваются на пересечение, поэтому
    границы сходятся крест-накрест. У вакансии без чисел обе колонки пусты,
    и сравнение с пустотой отсеивает её само.
    """
    clauses: list = []
    if f.score_min is not None:
        clauses.append(Vacancy.score >= f.score_min)
    if f.score_max is not None:
        clauses.append(Vacancy.score <= f.score_max)
    if f.salary_min is not None:
        clauses.append(Vacancy.salary_max >= f.salary_min)
    if f.salary_max is not None:
        clauses.append(Vacancy.salary_min <= f.salary_max)
    if f.date_from is not None:
        clauses.append(activity_ts >= f.date_from)
    if f.date_to is not None:
        clauses.append(activity_ts <= f.date_to)
    return clauses


def _column_clauses(f: VacancyFilter) -> list:
    """Условия по одиночным колонкам вакансии."""
    clauses: list = []
    if f.grade:
        clauses.append(func.lower(Vacancy.grade).like(f"%{f.grade.lower()}%"))
    if f.remote:
        clauses.append(func.lower(Vacancy.remote).like(f"%{f.remote.lower()}%"))
    if f.hr_contact == "with":
        clauses.append(Vacancy.hr_id.is_not(None))
    elif f.hr_contact == "without":
        clauses.append(Vacancy.hr_id.is_(None))
    return clauses


def _where_and_joins(f: VacancyFilter, activity_ts) -> tuple[list, set[str]]:
    """Все условия отбора разом и имена соседей, без которых они не читаются.

    Соседи подтягиваются по требованию, а не всегда: список открывают без
    фильтров чаще, чем с ними, и три лишних соединения на каждой странице
    стоили бы дороже, чем ветвление здесь.
    """
    clauses: list = [PARSED_ONLY]
    joins: set[str] = set()
    for found, needed in (_search_clauses(f.search), _choice_clauses(f)):
        clauses.extend(found)
        joins.update(needed)
    clauses.extend(_range_clauses(f, activity_ts))
    clauses.extend(_column_clauses(f))
    return clauses, joins


async def list_vacancies(
    session: AsyncSession, filters: VacancyFilter
) -> tuple[list[Vacancy], bool]:
    """Вакансии в порядке, заданном отбором, и есть ли за ними ещё.

    Что можно отобрать — у `VacancyFilter`; метка активности, по которой
    идёт порядок, одна и та же у списка и у `list_vacancy_last_activity`.
    Недоразобранные строки не показываются вовсе: они существуют только
    потому, что конвейер прервался между заведением строки и записью
    разбора, а подберёт их следующий запуск —
    `IngestionPipeline.recover_orphan_vacancies`.

    Признак продолжения отдаётся ответом, а не выводится зовущим из длины
    страницы — почему, сказано у `paging.trim_page`.
    """
    f = filters
    stmt = _listing_stmt(f)
    if f.limit is not None:
        stmt = stmt.limit(f.limit + 1).offset(f.offset)
    rows = list((await session.scalars(stmt)).all())
    return trim_page(rows, f.limit)


def _listing_stmt(f: VacancyFilter):
    """Запрос списка без страницы: отбор, соседи и порядок.

    Соседние таблицы соединяются по требованию — какие именно, решает
    `_where_and_joins`: список открывают без отбора чаще, чем с ним. Сами же
    соседи вакансии (`VACANCY_NEIGHBOURS`) подтягиваются всегда — их рисует
    каждая строка.
    """
    event_agg, status_agg = _activity_aggs()
    activity_ts = _activity_ts(event_agg, status_agg)
    where_clauses, joins = _where_and_joins(f, activity_ts)
    stmt = (
        select(Vacancy)
        .outerjoin(event_agg, event_agg.c.vid == Vacancy.id)
        .outerjoin(status_agg, status_agg.c.vid == Vacancy.id)
    )
    if "hr" in joins:
        stmt = stmt.outerjoin(HR, HR.id == Vacancy.hr_id)
    if "company" in joins:
        stmt = stmt.outerjoin(Company, Company.id == Vacancy.company_id)
    if "channel" in joins:
        stmt = stmt.outerjoin(
            TelegramChannel, TelegramChannel.id == Vacancy.source_channel_id
        )
    return (
        stmt
        .where(*where_clauses)
        .options(*VACANCY_NEIGHBOURS)
        .order_by(*_order_for(f.sort, activity_ts))
    )


async def _channel_options(session: AsyncSession) -> list[str]:
    """Каналы, у которых есть хоть одна разобранная вакансия."""
    rows = await session.execute(
        select(TelegramChannel.username)
        .join(Vacancy, Vacancy.source_channel_id == TelegramChannel.id)
        .where(
            PARSED_ONLY,
            TelegramChannel.username.is_not(None),
        )
        .distinct()
    )
    return dedupe_first_wins([name for (name,) in rows.all()], str.lower)


async def _company_options(session: AsyncSession) -> list[str]:
    """Компании из отбора — и привязанные строкой, и названные в вакансии.

    Вторые берутся затем, что вакансия без привязанной компании иначе не
    попала бы в отбор своим названием вовсе.

    Ключ здесь `lower`, а у написаний той же компании в её карточке —
    `casefold`: одно название сравнивается двумя правилами. Расходятся они
    на «ß» и «İ», то есть сегодня недостижимо, и намеренным это никогда не
    объявлялось. Кто заведёт такое название, тот и сводит правила.
    """
    linked_rows = await session.execute(
        select(Company.name)
        .join(Vacancy, Vacancy.company_id == Company.id)
        .where(PARSED_ONLY, Company.name.is_not(None))
        .distinct()
    )
    raw_rows = await session.execute(
        select(Vacancy.company_name)
        .where(
            PARSED_ONLY,
            Vacancy.company_name.is_not(None),
        )
        .distinct()
    )
    return dedupe_first_wins(
        [
            name.strip()
            for source in (linked_rows.all(), raw_rows.all())
            for (name,) in source
            if name and name.strip() != "—"
        ],
        str.lower,
    )


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
    return {
        "channels": await _channel_options(session),
        "companies": await _company_options(session),
    }


async def list_vacancy_last_activity(
    session: AsyncSession, vacancy_ids: list[int]
) -> dict[int, datetime]:
    """Метка последней активности для каждой из названных вакансий.

    Источники те же и в том же порядке, что у сортировки списка: их перечень
    объявлен один раз в :func:`_activity_ts`.
    """
    ids = [int(x) for x in vacancy_ids if x is not None]
    if not ids:
        return {}

    event_agg, status_agg = _activity_aggs(ids)
    rows = (
        await session.execute(
            select(Vacancy.id, _activity_ts(event_agg, status_agg))
            .outerjoin(event_agg, event_agg.c.vid == Vacancy.id)
            .outerjoin(status_agg, status_agg.c.vid == Vacancy.id)
            .where(Vacancy.id.in_(ids))
        )
    ).all()
    return {
        int(v_id): ts
        for v_id, ts in rows
        if v_id is not None and ts is not None
    }
