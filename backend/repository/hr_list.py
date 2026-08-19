"""Перечни HR со счётчиками."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Company, HR, Message, Vacancy
from backend.payloads import HrWithCount

from backend.repository.blacklist_marks import active_blacklist_values, marked_by
from backend.repository.hr_card import LAST_VACANCY_ORDER, hr_blacklist_candidates
from backend.repository.hr_identify import HAS_TELEGRAM_IDENTITY
from backend.repository.messages import UNREAD_INCOMING
from backend.repository.paging import searched_page
from backend.repository.search import matches_search
from backend.repository.vacancies_common import (
    PARSED_ONLY,
    by_vacancy_count,
    with_vacancy_counts,
)


async def list_hrs_for_backfill(session: AsyncSession) -> list[HR]:
    """Все, до кого можно дотянуться в Telegram, — с них бот и догоняет.

    Одних людей, без отметки «докуда уже прочитано»: догон читает хвост
    переписки целиком и отбивает повторы номером сообщения, а границу сверки
    удалённого снимает своим запросом — по обеим сторонам, не по входящим.
    Отметка здесь была лишним обращением к базе на каждого человека, и на
    трёх сотнях собеседников это три сотни запросов в никуда.
    """
    return list(
        (await session.scalars(select(HR).where(HAS_TELEGRAM_IDENTITY))).all()
    )


def _hr_counts_query(sort_by: str):
    """Люди со счётчиком вакансий, в порядке, которого просит зовущий.

    ``"vacancy_count"`` (по умолчанию, окно связывания): счёт по убыванию,
    при равенстве по имени — плодовитые наверху, естественный порядок для
    выбора. ``"last_activity"`` (вкладка «Контакты/HR»): последняя переписка
    по убыванию, пустые в конец, дальше по имени.
    """
    if sort_by != "last_activity":
        return with_vacancy_counts(HR, Vacancy.hr_id, HR.name)
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
    # Поверх общего запроса, а не вторым его написанием: счёт вакансий у
    # обеих веток один и тот же, и разойдись они, вкладка контактов показывала
    # бы не то число, что подборщик. Прежний порядок при этом снимается —
    # здесь наверху не плодовитые, а те, с кем говорили последними.
    return (
        with_vacancy_counts(HR, Vacancy.hr_id, HR.name)
        .outerjoin(last_act_subq, last_act_subq.c.hr_id == HR.id)
        .group_by(last_act_subq.c.last_act)
        .order_by(None)
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


async def list_hr_with_counts(
    session: AsyncSession,
    search: str | None = None,
    *,
    limit: int | None = None,
    offset: int = 0,
    sort_by: str = "vacancy_count",
) -> tuple[list[HrWithCount], bool]:
    """Страница людей со счётом вакансий и последней компанией, и есть ли за ней ещё.

    Зовут двое — подборщик «Связать с HR» и вкладка контактов.

    **Доводов пять, и свёртке они не подлежат.** Три из них — страница и
    отбор, и группа тут настоящая, но объявление под неё уже есть в мосте
    (`client/bridge/page.py`), вместе с режимом показа и порядковым знаком —
    тем, чего репозиторию знать нельзя. Второе такое же объявление в
    репозитории разошлось бы с первым молча: соседний перечень компаний
    просит страницу теми же словами и уже сегодня без порядка.

    Договор с зовущим разошёлся по помощникам: порядок — ``sort_by``,
    :func:`_hr_counts_query`; отбор по ``search`` и страница ``limit``/
    ``offset`` — `paging.searched_page`; ``last_company_name`` —
    :func:`_last_company_by_hr`. Без предела возвращается всё: так это окно
    связывания и звало всегда.
    """
    rows = (await session.execute(_hr_counts_query(sort_by))).all()
    counts, has_more = searched_page(
        rows,
        lambda row: matches_search(search, row[0].name, row[0].telegram_username),
        limit,
        offset,
    )
    last_co = await _last_company_by_hr(session)
    unread_by_hr = await _unread_by_hr(session)
    bl_values = await active_blacklist_values(session, "hr")
    return [
        HrWithCount(
            hr=hr,
            vacancy_count=int(cnt or 0),
            last_company_name=last_co.get(hr.id),
            unread_count=unread_by_hr.get(hr.id, 0),
            is_blacklisted=marked_by(hr_blacklist_candidates(hr), bl_values),
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
            .order_by(*by_vacancy_count(HR.name))
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
