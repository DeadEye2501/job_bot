"""Отметка предмета в чёрном списке, поставленная из его карточки.

Кнопка «в чёрный список» и обратная ей стоят на четырёх карточках — человека,
компании, канала и агрегатора, — и делают одно: найти запись, взять написание, которым
предмет в списке числится, завести отметку или погасить её. Дело одно, и тело
у него одно: разнесённое по кнопкам, оно расходилось бы в мелочах, и одна
карточка отмечала бы иначе соседней.

Отличие от соседей по пакету: `blacklist.py` — это экран самого списка, где
записи заводят, правят и удаляют по их собственным номерам; здесь предмет
называет себя сам, и номер у него свой, а не списочный.

Предметы описаны таблицей: род, модель, имя ключа в ответе, слова отказов и
объявление перечня написаний. Слова у каждого свои не по недосмотру — на трёх
экранах человек читает про разные вещи.

Обвязка кнопок живёт здесь же: сессия, зов и весть о том, что списки контактов
устарели. Отметка отсева запечена в строках всех предметов, и весть у них
общая: написанная в самих кнопках, она терялась бы у той, где её забыли.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.models import HR, Aggregator, Company, TelegramChannel
from backend.repository import (
    aggregators as aggregators_repo,
    blacklist as blacklist_repo,
    channels as channels_repo,
    companies_card,
    hr_card,
)
from backend.repository.blacklist_marks import BlacklistMark, preferred_blacklist_value
from client.bridge.answer import Denied
from client.bridge.refusals import NO_AGGREGATOR, NO_CHANNEL, NO_COMPANY, NO_HR, WEB_SEARCH_UNMARKED


@dataclass(frozen=True)
class MarkSubject:
    """Чем предмет называет себя чёрному списку и что окно о нём читает.

    Род и перечень написаний берутся из объявления предмета в репозитории
    (`BlacklistMark`): по ним же отметку ищут чип карточки и списки, и
    отмечать здесь другим перечнем значило бы ставить отметку, которой они не
    увидят.
    """

    blacklist: BlacklistMark
    model: type
    key: str
    missing: str
    unnamed: str


HR_MARK = MarkSubject(
    blacklist=hr_card.HR_BLACKLIST,
    model=HR,
    key="hr_id",
    missing=NO_HR,
    unnamed="У HR нет ни @username, ни telegram_user_id.",
)

COMPANY_MARK = MarkSubject(
    blacklist=companies_card.COMPANY_BLACKLIST,
    model=Company,
    key="company_id",
    missing=NO_COMPANY,
    unnamed="У компании нет имени.",
)

CHANNEL_MARK = MarkSubject(
    blacklist=channels_repo.CHANNEL_BLACKLIST,
    model=TelegramChannel,
    key="channel_id",
    missing=NO_CHANNEL,
    unnamed="У канала нет @username.",
)

AGGREGATOR_MARK = MarkSubject(
    blacklist=aggregators_repo.AGGREGATOR_BLACKLIST,
    model=Aggregator,
    key="aggregator_id",
    missing=NO_AGGREGATOR,
    unnamed=WEB_SEARCH_UNMARKED,
)


async def marked(hub, subject: MarkSubject, entity_id: int) -> dict:
    """Отметить предмет и сказать окну, что списки контактов устарели.

    Обвязка вокруг `mark` — сессия и весть — была написана трижды, по разу на
    карточку, и различалась только предметом. Отметка отсева запечена в строках
    людей, компаний и каналов, поэтому весть общая: без неё соседние экраны
    показывали бы предмет незаслонённым.
    """
    async with hub.session_factory() as session:
        done = await mark(session, subject, entity_id)
    hub.events.add("contacts_lists_changed")
    return done


async def unmarked(hub, subject: MarkSubject, entity_id: int) -> dict:
    """Снять отметку с предмета и сказать окну то же самое.

    Пара к `marked` и по тому же доводу: три тела на три карточки различались
    одним предметом.
    """
    async with hub.session_factory() as session:
        done = await unmark(session, subject, entity_id)
    hub.events.add("contacts_lists_changed")
    return done


async def mark(session, subject: MarkSubject, entity_id: int) -> dict:
    """Завести отметку и отдать написание, под которым она легла.

    Написание берётся первым из перечня — тем же, по которому отметку потом
    и ищут. Исход возвращается словом: карточка рисует «уже был в списке» и
    «вернули в список» по-разному, и признака «завели ли» ей мало.

    Отказ бросается, а не возвращается: возврат занят нагрузкой, а конверт
    складывает `reply` у зовущего.
    """
    row = await session.get(subject.model, entity_id)
    if row is None:
        raise Denied(subject.missing, action="blacklist", **{subject.key: entity_id})
    value = preferred_blacklist_value(subject.blacklist.candidates(row))
    if value is None:
        raise Denied(subject.unnamed, action="blacklist", **{subject.key: entity_id})
    _, outcome = await blacklist_repo.create_blacklist(
        session, kind=subject.blacklist.kind, value=value,
    )
    await session.commit()
    return {
        "action": "blacklist",
        subject.key: entity_id,
        "value": value,
        "existed": outcome != "created",
        "was_inactive": outcome == "reactivated",
    }


async def unmark(session, subject: MarkSubject, entity_id: int) -> dict:
    """Погасить отметки предмета и сказать, сколько их погасло.

    Гасятся все написания сразу, а не одно: запись могли завести под ником,
    а предмет с тех пор остался с одним номером — и чип в карточке продолжал
    бы гореть по написанию, которого кнопка уже не видит.

    Отказ бросается по тому же доводу, что и у соседки выше.
    """
    row = await session.get(subject.model, entity_id)
    if row is None:
        raise Denied(subject.missing, action="unblacklist", **{subject.key: entity_id})
    candidates = subject.blacklist.candidates(row)
    if not candidates:
        raise Denied(subject.unnamed, action="unblacklist", **{subject.key: entity_id})
    updated = await blacklist_repo.deactivate_blacklist_values(
        session, subject.blacklist.kind, candidates,
    )
    await session.commit()
    return {
        "action": "unblacklist",
        subject.key: entity_id,
        "updated": updated,
    }
