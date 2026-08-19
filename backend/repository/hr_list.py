"""Перечни HR со счётчиками."""

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Company, HR, Message, Vacancy
from backend.payloads import HrWithCount

from backend.repository.blacklist_marks import active_blacklist_values
from backend.repository.hr_card import LAST_VACANCY_ORDER, hr_blacklist_candidates
from backend.repository.hr_identify import HAS_TELEGRAM_IDENTITY
from backend.repository.messages import UNREAD_INCOMING
from backend.repository.paging import slice_page
from backend.repository.search import matches_search
from backend.repository.vacancies_common import PARSED_ONLY

_HR_BY_VACANCY_COUNT = (func.count(Vacancy.id).desc(), HR.name.asc())
"""Порядок «кто принёс больше вакансий», а при равенстве — по имени.

Одно объявление на два перечня — общий и по компании: разойдись они, один и
тот же человек стоял бы в двух списках по-разному без всякой причины.
"""


async def _with_last_incoming_id(
    session: AsyncSession, hrs: list[HR]
) -> list[tuple[HR, int]]:
    """Каждому человеку — наибольший `tg_message_id` входящего, что у нас
    уже есть, или ноль. С этой границы догон и продолжает читать.
    """
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


async def list_hrs_for_backfill(session: AsyncSession) -> list[HR]:
    """Все, до кого можно дотянуться в Telegram, — с них бот и догоняет.

    Шире `list_open_hr_chats`: тот берёт только тех, кому мы писали первыми.

    Одних людей, без отметки «докуда уже прочитано»: догон читает хвост
    переписки целиком и отбивает повторы номером сообщения, а границу сверки
    удалённого снимает своим запросом — по обеим сторонам, не по входящим.
    Отметка здесь была лишним обращением к базе на каждого человека, и на
    трёх сотнях собеседников это три сотни запросов в никуда.
    """
    return list(
        (await session.scalars(select(HR).where(HAS_TELEGRAM_IDENTITY))).all()
    )


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
    return await _with_last_incoming_id(session, hrs)


def _hr_counts_query(sort_by: str):
    """Люди со счётчиком вакансий, в порядке, которого просит зовущий.

    ``"vacancy_count"`` (по умолчанию, окно связывания): счёт по убыванию,
    при равенстве по имени — плодовитые наверху, естественный порядок для
    выбора. ``"last_activity"`` (вкладка «Контакты/HR»): последняя переписка
    по убыванию, пустые в конец, дальше по имени.
    """
    if sort_by != "last_activity":
        return (
            select(HR, func.count(Vacancy.id).label("cnt"))
            .outerjoin(Vacancy, and_(Vacancy.hr_id == HR.id, PARSED_ONLY))
            .group_by(HR.id)
            .order_by(*_HR_BY_VACANCY_COUNT)
        )
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
    return (
        select(HR, func.count(Vacancy.id).label("cnt"))
        .outerjoin(Vacancy, and_(Vacancy.hr_id == HR.id, PARSED_ONLY))
        .outerjoin(last_act_subq, last_act_subq.c.hr_id == HR.id)
        .group_by(HR.id, last_act_subq.c.last_act)
        .order_by(
            last_act_subq.c.last_act.desc().nullslast(),
            HR.name.asc(),
        )
    )


async def _last_company_by_hr(session: AsyncSession) -> dict[int, str]:
    """Компания последней вакансии каждого человека.

    Пусто, если у самой свежей вакансии компании нет, — даже когда она была
    у вакансий постарше. Свежая выигрывает нарочно: в окне связывания старое
    окружение вводит в заблуждение.
    """
    latest_subq = (
        select(
            Vacancy.hr_id.label("hr_id"),
            Vacancy.company_id.label("company_id"),
            func.row_number()
            .over(partition_by=Vacancy.hr_id, order_by=LAST_VACANCY_ORDER)
            .label("rn"),
        )
        .where(Vacancy.hr_id.is_not(None))
        .subquery()
    )
    rows = (
        await session.execute(
            select(latest_subq.c.hr_id, Company.name)
            .join(Company, Company.id == latest_subq.c.company_id)
            .where(latest_subq.c.rn == 1)
        )
    ).all()
    return {hr_id: name for hr_id, name in rows}


async def _unread_by_hr(session: AsyncSession) -> dict[int, int]:
    """Сколько непрочитанных входящих у каждого человека — для лаймового значка.

    Один запрос с группировкой: раздельные счёты дали бы N обращений к базе
    на один показ списка.
    """
    rows = (
        await session.execute(
            select(Message.hr_id, func.count(Message.id))
            .where(
                Message.hr_id.is_not(None),
                *UNREAD_INCOMING,
            )
            .group_by(Message.hr_id)
        )
    ).all()
    return {hr_id: int(n) for hr_id, n in rows}


def _found_page(rows, search: str | None, limit: int | None, offset: int):
    """Строки, подходящие под искомое, из них страница и есть ли за ней ещё.

    Отбор идёт в Python (см. :func:`backend.repository.search.matches_search`),
    и страница отрезается после него — почему, сказано у `paging.slice_page`.
    Без предела возвращается всё: так это окно связывания и звало всегда.
    """
    found = [
        (hr, cnt)
        for hr, cnt in rows
        if matches_search(search, hr.name, hr.telegram_username)
    ]
    return slice_page(found, limit, offset)


async def list_hr_with_counts(
    session: AsyncSession,
    search: str | None = None,
    *,
    limit: int | None = None,
    offset: int = 0,
    sort_by: str = "vacancy_count",
) -> tuple[list[HrWithCount], bool]:
    """Страница людей со счётом вакансий и последней компанией, и есть ли за ней ещё.

    Used by the "Связать с HR" picker AND the Contacts/HR pane (05).

    Договор с зовущим разошёлся по помощникам: порядок — ``sort_by``,
    :func:`_hr_counts_query`; отбор по ``search`` и страница ``limit``/
    ``offset`` — :func:`_found_page`; ``last_company_name`` —
    :func:`_last_company_by_hr`.
    """
    rows = (await session.execute(_hr_counts_query(sort_by))).all()
    counts, has_more = _found_page(rows, search, limit, offset)
    last_co = await _last_company_by_hr(session)
    unread_by_hr = await _unread_by_hr(session)
    bl_values = await active_blacklist_values(session, "hr")
    return [
        HrWithCount(
            hr=hr,
            vacancy_count=int(cnt or 0),
            last_company_name=last_co.get(hr.id),
            unread_count=unread_by_hr.get(hr.id, 0),
            is_blacklisted=any(
                c in bl_values for c in hr_blacklist_candidates(hr)
            ),
        )
        for hr, cnt in counts
    ], has_more


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
            .where(Vacancy.company_id == company_id, PARSED_ONLY)
            .group_by(HR.id)
            .order_by(*_HR_BY_VACANCY_COUNT)
        )
    ).all()
    return [(hr, int(cnt or 0)) for hr, cnt in rows]


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
            .where(*UNREAD_INCOMING)
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
