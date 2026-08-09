"""Перечни HR со счётчиками."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Company, HR, Message, Vacancy
from backend.payloads import HrWithCount

from backend.repository.blacklist_marks import active_blacklist_values
from backend.repository.hr_card import hr_blacklist_candidates
from backend.repository.messages import UNREAD_INCOMING

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
    return await _with_last_incoming_id(session, hrs)


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
                *UNREAD_INCOMING,
            )
            .group_by(Message.hr_id)
        )
    ).all()
    unread_by_hr: dict[int, int] = {hr_id: int(n) for hr_id, n in unread_rows}

    bl_values = await active_blacklist_values(session, "hr")

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
