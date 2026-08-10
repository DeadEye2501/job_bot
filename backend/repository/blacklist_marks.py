"""Активные строки чёрного списка, по которым предметы получают отметку."""

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Blacklist


def active_mark_of(kind: str, candidates: list[str]):
    """Условие «предмет отмечен»: активная строка своего рода под любым из
    написаний предмета.

    Что считать отметкой, решается здесь одним объявлением: по этому же
    условию отметку и снимают (`blacklist.deactivate_blacklist_values`), а
    разойдись эти два правила — снятие переставало бы гасить то, что
    карточка показывает чипом.
    """
    return and_(
        Blacklist.kind == kind,
        Blacklist.value.in_(candidates),
        Blacklist.active.is_(True),
    )


async def active_blacklist_value(
    session: AsyncSession, kind: str, candidates: list[str]
) -> str | None:
    """Точный `value` активной строки, под которой предмет числится в
    чёрном списке, — для чипа в карточке. None, если не числится.

    Порядок по возрастанию `id` не украшение: написаний у предмета бывает
    несколько сразу (редко — повторное заведение после правки схемы), и без
    него подпись чипа меняла бы значение от загрузки к загрузке.
    """
    if not candidates:
        return None
    row = (
        await session.scalars(
            select(Blacklist)
            .where(active_mark_of(kind, candidates))
            .order_by(Blacklist.id.asc())
            .limit(1)
        )
    ).first()
    return row.value if row else None


async def active_blacklist_values(session: AsyncSession, kind: str) -> set[str]:
    """Все активные значения этого рода одним запросом: перечням нужна
    проверка вхождения на каждую строку, а не запрос на каждую.
    """
    return set(
        (
            await session.scalars(
                select(Blacklist.value).where(
                    Blacklist.kind == kind,
                    Blacklist.active.is_(True),
                )
            )
        ).all()
    )


def preferred_blacklist_value(candidates: list[str]) -> str | None:
    """Написание, которое кнопка «в чёрный список» и запишет.

    Первое из перечня: перечень собран в порядке предпочтения — ник
    читается на экране, а номер годится, когда ника нет. Порядок его и
    есть договор, менять перечень значит менять то, что пишет кнопка.
    """
    return candidates[0] if candidates else None
