"""Отбор вакансий для списка на экране."""

import logging
from datetime import datetime

from sqlalchemy import String, and_, case, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.spellings import dedupe_first_wins
from backend.models import (
    Company,
    HR,
    TelegramChannel,
    Vacancy,
    VacancyContact,
    VacancyStatus,
    status_code,
)
from backend.payloads import VacancyFilter
from backend.repository.paging import trim_page
from backend.repository.vacancies_activity import (
    activity_aggs,
    activity_ts,
    join_activity,
)
from backend.repository.vacancies_card import VACANCY_NEIGHBOURS
from backend.repository.vacancies_common import PARSED_ONLY

logger = logging.getLogger(__name__)

_STATUS_BY_CODE = {status_code(s): s for s in VacancyStatus}
"""Положение дел по коду, которым его называет окно.

Собирается правилом (`models.status_code`), а не выписывается руками: таблица
руками разошлась бы с перечислением на первом же новом положении дел, и отбор
по нему перестал бы работать молча.
"""


# Обещание этого порядка — воронка с конца: чем ближе к оферу, тем выше. Тест
# и приглашение подняты над «в процессе» нарочно: там ход за человеком, а «в
# процессе» — ожидание ответа HR (`domain/transitions.py`). Сквозным правилом
# «ход за человеком» не служит: «новая» лежит ниже «отклика», хотя отправлять
# отклик тоже человеку. Второй перечень обещает обратное, «сначала новые», и
# идёт по воронке с её начала.
#
# У мини-списка канала (`vacancies_mini.py`) обещание другое — «по ходу
# воронки»: там «в процессе» стоит выше теста с приглашением, а «не подходит»
# уходит в самый низ. Расходятся обе половины перечня — и активная середина, и
# холодный хвост, у которого принципа нет ни здесь, ни там. Расхождение
# подтверждено человеком 19.08 и намеренно: сводить таблицы в одну не надо.
#
# Зеркала у самой сортировки в разметке нет — порядок выдачи целиком на
# стороне запроса. Свои перечни статусов у окна есть (`state/stats.js`), но они
# о другом: там кольцо воронки, а не порядок списка.
# Положения дел вне перечня уходят в хвост (999).
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


def _order_for(sort: str, freshness):
    """Порядок выдачи по ключу сортировки; незнакомый ключ — «сначала свежие».

    Номер строки идёт последним у каждого ключа: у меток активности бывают
    совпадения, и без него порядок двух таких строк решался бы случаем — от
    страницы к странице они менялись бы местами.

    Незнакомый ключ доходит до последней строки и получает «сначала свежие».
    """
    if sort == "oldest":
        return (freshness.asc().nulls_last(), Vacancy.id.asc())
    if sort == "score_desc":
        return (
            Vacancy.score.desc().nulls_last(),
            freshness.desc(),
            Vacancy.id.desc(),
        )
    if sort == "score_asc":
        return (
            Vacancy.score.asc().nulls_last(),
            freshness.desc(),
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
        return (priority.asc(), freshness.desc(), Vacancy.id.desc())
    return (freshness.desc().nulls_last(), Vacancy.id.desc())


_LIKE_ESCAPE = "\\"

_LIKE_SPECIALS = (_LIKE_ESCAPE, "%", "_")
"""Знаки, которые `LIKE` читает как образец. Знак экранирования назван первым:
обезвредь его вторым, и он удвоил бы уже проставленные слэши."""


def _like_anywhere(text: str) -> str:
    """Образец «где-то внутри» из того, что набрал человек.

    Знаки образца обезвреживаются: для человека `%` и `_` — обычные символы
    из зарплаты и из ника, а не язык запроса. Незакрытый `%` превращает любой
    поиск в «выдать всё», и вместо находки человек видит всю базу.

    Регистр сводится здесь же и только здесь: обе стороны сравнения обязаны
    складываться одинаково, а на стороне базы стоит `lower` из
    `adapters/db.py` — он и кириллицу понимает.

    Зовущему остаётся передать `escape=_LIKE_ESCAPE`: без этого довода база не
    узнает, чем именно мы обезвредили.
    """
    escaped = text.strip().lower()
    for ch in _LIKE_SPECIALS:
        escaped = escaped.replace(ch, _LIKE_ESCAPE + ch)
    return f"%{escaped}%"


def _search_clauses(search: str | None) -> tuple[list, set[str]]:
    """Условие поиска подстрокой и соседи, которых оно требует.

    Ищется по колонкам строки, по сырому JSON стека — по всему, что человек
    видит в строке списка, — и по контактам вакансии: их видно в карточке, а
    вспоминают вакансию часто по адресу, на который откликались. Имя HR и имя компании лежат в своих таблицах,
    поэтому соседи называются здесь же: знание «какое условие без какого
    соседа не читается» живёт при самом условии, а не у зовущего.
    """
    if not search or not search.strip():
        return [], set()
    q = _like_anywhere(search)
    matched = or_(
        func.lower(Vacancy.title).like(q, escape=_LIKE_ESCAPE),
        func.lower(Vacancy.description).like(q, escape=_LIKE_ESCAPE),
        func.lower(Vacancy.company_name).like(q, escape=_LIKE_ESCAPE),
        func.lower(Vacancy.notes).like(q, escape=_LIKE_ESCAPE),
        func.lower(Vacancy.salary).like(q, escape=_LIKE_ESCAPE),
        func.lower(Vacancy.grade).like(q, escape=_LIKE_ESCAPE),
        func.lower(HR.name).like(q, escape=_LIKE_ESCAPE),
        func.lower(HR.telegram_username).like(q, escape=_LIKE_ESCAPE),
        func.lower(Company.name).like(q, escape=_LIKE_ESCAPE),
        func.lower(cast(Vacancy.stack, String)).like(q, escape=_LIKE_ESCAPE),
        Vacancy.id.in_(
            select(VacancyContact.vacancy_id).where(
                func.lower(VacancyContact.value).like(q, escape=_LIKE_ESCAPE)
            )
        ),
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
        unknown = [code for code in f.statuses if code not in _STATUS_BY_CODE]
        if unknown:
            # Молча отбросить нельзя: для человека это «фильтр нажат и не
            # действует», и увидеть причину ему негде.
            logger.warning("unknown status codes in filter: %s", unknown)
        enum_values = [_STATUS_BY_CODE[s] for s in f.statuses if s in _STATUS_BY_CODE]
        if enum_values:
            clauses.append(Vacancy.status.in_(enum_values))
    if f.channels:
        cleaned = [c.lower() for c in f.channels if c]
        if cleaned:
            clauses.append(func.lower(TelegramChannel.username).in_(cleaned))
            joins.add("channel")
    if f.companies:
        cleaned = [c.strip().lower() for c in f.companies if c and c.strip()]
        if cleaned:
            # Края обрезаются с обеих сторон сравнения: выпадающий список их
            # обрезает (см. :func:`_company_options`), и название, приехавшее
            # из поста с висячим пробелом, иначе не находило бы собственную
            # вакансию — а своего написания список не предлагает вовсе.
            clauses.append(
                or_(
                    func.trim(func.lower(Company.name)).in_(cleaned),
                    func.trim(func.lower(Vacancy.company_name)).in_(cleaned),
                )
            )
            joins.add("company")
    return clauses, joins


def _salary_clauses(f: VacancyFilter) -> list:
    """Условия по окну зарплаты.

    Окно и вилка вакансии сравниваются на пересечение, поэтому границы
    сходятся крест-накрест. У вакансии без чисел обе колонки пусты, и
    сравнение с пустотой отсеивает её само.

    Одна названная граница — не то же самое, что ни одной: «от 300 000»
    потолка не имеет вовсе, и ставить ему те же триста тысяч значит прятать
    вакансию от отбора «от 400 000». Пустая сторона при названной второй
    отбору не противоречит и потому его проходит.
    """
    clauses: list = []
    if f.salary_min is not None:
        clauses.append(
            or_(
                Vacancy.salary_max >= f.salary_min,
                and_(
                    Vacancy.salary_max.is_(None),
                    Vacancy.salary_min.is_not(None),
                ),
            )
        )
    if f.salary_max is not None:
        clauses.append(
            or_(
                Vacancy.salary_min <= f.salary_max,
                and_(
                    Vacancy.salary_min.is_(None),
                    Vacancy.salary_max.is_not(None),
                ),
            )
        )
    return clauses


def _range_clauses(f: VacancyFilter, freshness) -> list:
    """Условия по числовым и временным границам."""
    clauses: list = []
    if f.score_min is not None:
        clauses.append(Vacancy.score >= f.score_min)
    if f.score_max is not None:
        clauses.append(Vacancy.score <= f.score_max)
    clauses.extend(_salary_clauses(f))
    if f.date_from is not None:
        clauses.append(freshness >= f.date_from)
    if f.date_to is not None:
        clauses.append(freshness <= f.date_to)
    return clauses


def _column_clauses(f: VacancyFilter) -> list:
    """Условия по одиночным колонкам вакансии."""
    clauses: list = []
    if f.grade:
        clauses.append(
            func.lower(Vacancy.grade).like(
                _like_anywhere(f.grade), escape=_LIKE_ESCAPE
            )
        )
    if f.remote:
        clauses.append(
            func.lower(Vacancy.remote).like(
                _like_anywhere(f.remote), escape=_LIKE_ESCAPE
            )
        )
    if f.hr_contact == "with":
        clauses.append(Vacancy.hr_id.is_not(None))
    elif f.hr_contact == "without":
        clauses.append(Vacancy.hr_id.is_(None))
    return clauses


def _where_and_joins(f: VacancyFilter, freshness) -> tuple[list, set[str]]:
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
    clauses.extend(_range_clauses(f, freshness))
    clauses.extend(_column_clauses(f))
    return clauses, joins


async def list_vacancies(
    session: AsyncSession, filters: VacancyFilter
) -> tuple[list[Vacancy], bool]:
    """Вакансии в порядке, заданном отбором, и есть ли за ними ещё.

    Что можно отобрать — у `VacancyFilter`; метка активности, по которой
    идёт порядок, одна и та же у списка и у `list_vacancy_last_activity`.
    Недоразобранные строки не показываются вовсе: приговора у них ещё нет —
    либо конвейер прервался между заведением строки и записью разбора, либо
    объявление ждёт статью по ссылке. Возвращается к ним каждый полный оборот
    цикла — `IngestionPipeline.recover_orphan_vacancies`.

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
    aggs = activity_aggs()
    freshness = activity_ts(aggs)
    where_clauses, joins = _where_and_joins(f, freshness)
    stmt = join_activity(select(Vacancy), aggs)
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
        .order_by(*_order_for(f.sort, freshness))
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
    объявлен один раз, в `vacancies_activity`.
    """
    ids = [int(x) for x in vacancy_ids if x is not None]
    if not ids:
        return {}

    aggs = activity_aggs(ids)
    rows = (
        await session.execute(
            join_activity(
                select(Vacancy.id, activity_ts(aggs)), aggs
            ).where(Vacancy.id.in_(ids))
        )
    ).all()
    return {
        int(v_id): ts
        for v_id, ts in rows
        if v_id is not None and ts is not None
    }
