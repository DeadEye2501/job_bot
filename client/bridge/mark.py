"""Отметка предмета в чёрном списке, поставленная из его карточки.

Кнопка «в чёрный список» и обратная ей стоят на трёх карточках — человека,
компании и канала, — и делают одно: найти запись, взять написание, которым
предмет в списке числится, завести отметку или погасить её. Шесть тел этого
одного дела разошлись ровно одной строкой на все шесть, и та строка была
поправкой поля модели руками.

Отличие от соседей по пакету: `blacklist.py` — это экран самого списка, где
записи заводят, правят и удаляют по их собственным номерам; здесь предмет
называет себя сам, и номер у него свой, а не списочный.

Предметы описаны таблицей: род, модель, имя ключа в ответе, слова отказов и
объявление перечня написаний. Слова у каждого свои не по недосмотру — на трёх
экранах человек читает про разные вещи.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from backend.models import HR, Company, TelegramChannel
from backend.repository import (
    blacklist as blacklist_repo,
    channels as channels_repo,
    companies_card,
    hr_card,
)
from backend.repository.blacklist_marks import preferred_blacklist_value
from client.bridge.answer import _err, _ok
from client.bridge.refusals import NO_CHANNEL, NO_COMPANY, NO_HR


@dataclass(frozen=True)
class MarkSubject:
    """Чем предмет называет себя чёрному списку и что окно о нём читает."""

    kind: str
    model: type
    key: str
    missing: str
    unnamed: str
    candidates: Callable[[object], list[str]]


HR_MARK = MarkSubject(
    kind="hr",
    model=HR,
    key="hr_id",
    missing=NO_HR,
    unnamed="У HR нет ни @username, ни telegram_user_id.",
    candidates=hr_card.hr_blacklist_candidates,
)

COMPANY_MARK = MarkSubject(
    kind="company",
    model=Company,
    key="company_id",
    missing=NO_COMPANY,
    unnamed="У компании нет имени.",
    candidates=companies_card.company_blacklist_candidates,
)

CHANNEL_MARK = MarkSubject(
    kind="channel",
    model=TelegramChannel,
    key="channel_id",
    missing=NO_CHANNEL,
    unnamed="У канала нет @username.",
    candidates=channels_repo.channel_blacklist_candidates,
)


async def mark(session, subject: MarkSubject, entity_id: int) -> tuple[str, bool]:
    """Завести отметку; вторым — дошло ли дело до записи.

    Написание берётся первым из перечня — тем же, по которому отметку потом
    и ищут. Исход возвращается словом: карточка рисует «уже был в списке» и
    «вернули в список» по-разному, и признака «завели ли» ей мало.

    Второй член кортежа — не «менялось ли», а «не отказ»: по нему зовущий
    решает, гнать ли окно перечитывать списки. Повторное нажатие на уже
    отмеченном предмете ничего не меняет, но списки перечитать просит — как
    и раньше, потому что чип в карточке рисуется по ним.
    """
    row = await session.get(subject.model, entity_id)
    if row is None:
        return _err(subject.missing, action="blacklist", **{subject.key: entity_id}), False
    value = preferred_blacklist_value(subject.candidates(row))
    if value is None:
        return _err(
            subject.unnamed, action="blacklist", **{subject.key: entity_id}
        ), False
    _, outcome = await blacklist_repo.create_blacklist(
        session, kind=subject.kind, value=value,
    )
    await session.commit()
    return _ok({
        "action": "blacklist",
        subject.key: entity_id,
        "value": value,
        "existed": outcome != "created",
        "was_inactive": outcome == "reactivated",
    }), True


async def unmark(session, subject: MarkSubject, entity_id: int) -> tuple[str, bool]:
    """Погасить отметки предмета; вторым — дошло ли дело до записи.

    Гасятся все написания сразу, а не одно: запись могли завести под ником,
    а предмет с тех пор остался с одним номером — и чип в карточке продолжал
    бы гореть по написанию, которого кнопка уже не видит.
    """
    row = await session.get(subject.model, entity_id)
    if row is None:
        return _err(
            subject.missing, action="unblacklist", **{subject.key: entity_id}
        ), False
    candidates = subject.candidates(row)
    if not candidates:
        return _err(
            subject.unnamed, action="unblacklist", **{subject.key: entity_id}
        ), False
    updated = await blacklist_repo.deactivate_blacklist_values(
        session, subject.kind, candidates,
    )
    await session.commit()
    return _ok({
        "action": "unblacklist",
        subject.key: entity_id,
        "updated": updated,
    }), True
