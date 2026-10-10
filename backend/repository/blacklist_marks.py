"""Активные строки чёрного списка, по которым предметы получают отметку."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Blacklist, HR
from backend.models.settings import AGGREGATOR_KIND, HR_KIND

_ACCOUNT_MARK_PREFIX = "user_id:"


def account_mark(telegram_user_id: int) -> str:
    """Написание отметки, привязанной к учётной записи Telegram.

    Живёт здесь, а не у карточки человека: тем же написанием отметку и пишут,
    и разбирают обратно (`_nicknames_of_marked_people`). Разойдись эти двое —
    отсев постов по нику отвалился бы молча, а на экранах всё выглядело бы
    работающим.
    """
    return f"{_ACCOUNT_MARK_PREFIX}{telegram_user_id}"


def nickname_mark(telegram_username: str) -> str:
    """Написание отметки, привязанной к нику Telegram."""
    return f"@{telegram_username}"


def _account_id_of(value: str) -> int | None:
    """Номер учётной записи из написания отметки; None — написание другое."""
    if not value.startswith(_ACCOUNT_MARK_PREFIX):
        return None
    tail = value[len(_ACCOUNT_MARK_PREFIX):]
    # `isascii` не украшение: значения этого рода набирают и руками, а
    # `"²".isdigit()` истина, тогда как `int("²")` роняет `ValueError` —
    # и уронил бы весь обход, читающий образцы перед циклом.
    return int(tail) if tail.isascii() and tail.isdigit() else None


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


async def _nicknames_of_marked_people(session: AsyncSession) -> list[str]:
    """Ники отмеченных людей — их написание для сверки с текстом объявления.

    Отметку человека кнопка держит на несменяемом номере учётной записи, а
    номер в тексте объявления не встречается никогда: по нему отсеиваются
    письма, но не посты. Ник встречается — и объявление, под которым назван
    отсеянный рекрутёр, отсеивается по нему.

    Ник берётся нынешний, из карточки, а не написание строки списка: сменился
    ник — отсев поедет за ним сам, чего написание в списке не умеет.
    """
    marked = (
        await session.scalars(
            select(Blacklist.value).where(
                Blacklist.kind == HR_KIND, Blacklist.active.is_(True)
            )
        )
    ).all()
    numbers = [n for n in (_account_id_of(v) for v in marked) if n is not None]
    if not numbers:
        return []
    nicknames = (
        await session.scalars(
            select(HR.telegram_username).where(HR.telegram_user_id.in_(numbers))
        )
    ).all()
    # Пустой ник отсеивается правдивостью, а не сверкой с `None`: заведение
    # сводит пустую строку к отсутствию, но пробейся она в колонку — образец
    # `"@"` ловил бы любую собачку в любом тексте, включая чужую почту.
    return [nickname_mark(nick) for nick in nicknames if nick]


async def load_active_blacklist_patterns(session: AsyncSession) -> list[str]:
    """Активные значения списка — образцы для сверки с текстом объявления.

    Род здесь почти не спрашивается: по тексту поста отсеивают и по названию
    компании, и по ключевому слову, и знать заранее, чем именно совпадёт,
    конвейеру незачем.

    Сайты в образцы не идут: отметка сайта отсеивает вакансии, которые на нём
    живут, — по адресу страницы и контактам (`aggregators.vacancy_barred_host`), —
    а пост, назвавший сайт мимоходом, остаётся чужой вакансией.

    Люди идут иначе: их написание в списке несменяемое и потому в тексте не
    встречается. К значениям добавляются ники отмеченных, иначе отметка на
    человеке гасила бы только письма (`_nicknames_of_marked_people`).
    """
    values = list(
        (
            await session.scalars(
                select(Blacklist.value).where(
                    Blacklist.active, Blacklist.kind != AGGREGATOR_KIND
                )
            )
        ).all()
    )
    return values + await _nicknames_of_marked_people(session)


def marked_by(candidates: list[str], values: set[str]) -> bool:
    """Отмечен ли предмет одной из заранее прочитанных строк.

    Перечням нужен ответ на каждую строку, и значения они читают разом
    (`active_blacklist_values`), а не запросом на предмет. Объявление одно на
    все перечни — людей, компаний, каналов и агрегаторов: разойдись они, один и тот же
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


@dataclass(frozen=True)
class BlacklistMark:
    """Отметка предмета одного рода: род и перечень написаний предмета.

    Пара объявляется у предмета один раз, а правила «чем отмечен», «отмечен
    ли» и «погасить отмеченные» живут здесь одним телом на всех: написанные у
    каждого предмета своей копией, они расходились бы родом или перечнем, и
    один и тот же предмет считался бы отмеченным на одном экране и чистым на
    другом.
    """

    kind: str
    candidates: Callable[[Any], list[str]]

    async def value(self, session: AsyncSession, row) -> str | None:
        """Написание действующей отметки предмета — для чипа и запретов; None — чист."""
        return await active_blacklist_value(session, self.kind, self.candidates(row))

    async def marked(self, session: AsyncSession) -> set[str]:
        """Написания всех действующих отметок рода — читаются разом для списка."""
        return await active_blacklist_values(session, self.kind)

    def among(self, row, values: set[str]) -> bool:
        """Отмечен ли предмет одной из заранее прочитанных строк своего рода."""
        return marked_by(self.candidates(row), values)

    async def switch_off(self, session: AsyncSession, model) -> int:
        """Выключить включённые источники под действующей отметкой; сколько выключено.

        Перебором строк, а не запросом: отметка ловит написания, которые
        собирает питон (у сайта — и поддомены), а источников единицы.
        Выключенные не трогаются. Сессию открывает и закрывает зовущий.
        """
        marked = await self.marked(session)
        if not marked:
            return 0
        rows = (await session.scalars(select(model).where(model.is_active.is_(True)))).all()
        barred = [row for row in rows if self.among(row, marked)]
        for row in barred:
            row.is_active = False
        return len(barred)
