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


async def load_active_blacklist_patterns(session: AsyncSession) -> list[str]:
    """Все активные значения списка, любого рода, — образцы для сверки с
    текстом объявления.

    Род здесь не спрашивается нарочно: по тексту поста отсеивают и по
    названию компании, и по ключевому слову, и знать заранее, чем именно
    совпадёт, конвейеру незачем.
    """
    return list(
        (
            await session.scalars(
                select(Blacklist.value).where(Blacklist.active)
            )
        ).all()
    )


def marked_by(candidates: list[str], values: set[str]) -> bool:
    """Отмечен ли предмет одной из заранее прочитанных строк.

    Перечням нужен ответ на каждую строку, и значения они читают разом
    (`active_blacklist_values`), а не запросом на предмет. Объявление одно на
    все три перечня — людей, компаний и каналов: разойдись они, один и тот же
    предмет считался бы отмеченным на одном экране и чистым на другом.
    """
    return any(c in values for c in candidates)


def preferred_blacklist_value(candidates: list[str]) -> str | None:
    """Написание, которое кнопка «в чёрный список» и запишет.

    Первое из перечня, а перечень собирает сам предмет — в порядке
    предпочтения. У человека впереди стоит несменяемый номер учётной записи:
    ник Telegram переписывает с каждым письмом, и отметка на нём слетала бы
    молча. Порядок перечня и есть договор: менять его значит менять то, что
    пишет кнопка.
    """
    return candidates[0] if candidates else None
