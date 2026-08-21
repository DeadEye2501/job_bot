"""Карточка контакта: то, что человек и компания делают одним и тем же телом.

Экрана два — «Контакты / HR» и «Контакты / Компании», — и восемь кнопок у них
общие до последней строки: перечень с поиском, короткий список вакансий,
подборщик слияния, само слияние, снос, заведение и две кнопки отсева. Своих у
человека две (карточка и правка полей), у компании три — те же две и список
людей, которых она приводила.
Различаются они именем ключа, объявлением репозитория и словом отказа, и пока
кнопки были написаны порознь, различия к этому не сводились: у человека снос
клал окну две вести, у компании ни одной.

Нагрузку окна тела читают сами, а не получают прочитанной. Так потому, что
иначе близнецами становились сами слоты: у каждого оставалось бы по четыре
строки разбора, отличающиеся именем ключа. Слот теперь — имя и одна строка,
и имя это по-прежнему написано литералом: по нему зов и ищут с обеих сторон.

Отличие от соседей по пакету: `pickers.py` — про модалку выбора, `mark.py` —
про отметку в чёрном списке; и то и другое зовут отсюда. Здесь сама карточка:
как её показывают, сливают и сносят.

Двух кнопок в таблице нет нарочно. `detail` у предметов разная целиком — она и
есть то, чем человек отличается от компании; `update` разъезжается на бедах:
компанию ловит занятое имя (`IntegrityError`), человека — негодный ник
(`ValueError`), и слова у них разные. Свести их значило бы завести таблицу
поведений вместо таблицы данных.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import logging

from backend.incoming import text_or_none
from client.bridge.answer import BAD_PAYLOAD, Denied, asked_id, bad_fields, reply
from client.bridge.page import read_page, read_search
from client.bridge.pickers import PickerSubject, merge_picker
from client.bridge.refusals import MERGE_INTO_SELF
from client.bridge.wire import _vacancy_mini_row_to_dict


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CardSubject:
    """Чем карточка человека отличается от карточки компании.

    Имена действий лежат литералами, а не собираются из предмета: их читает
    окно, и собранное имя не нашлось бы поиском по коду ни с той, ни с другой
    стороны. Приставка домена собирается — она уходит только в журнал.
    """

    picker: PickerSubject
    id_key: str
    missing: str
    domain: str
    page_limit: int | None
    listing: dict
    read_fields: Callable
    update_fields: tuple[str, ...]
    mini_vacancies: Callable
    merge_row: Callable
    delete_row: Callable
    create_row: Callable
    merge_action: str
    delete_action: str
    create_action: str
    news: tuple[str, ...]


def listed(hub, subject: CardSubject, payload: dict | None) -> dict:
    """Страница перечня с поиском.

    Строка та же, что в подборщике при вакансии: перечень у них общий, и
    разойдись формы, одна и та же запись выглядела бы на двух экранах
    по-разному.

    Лишние доводы перечня приходят таблицей: порядок «по последней активности»
    есть только у человека — у компании такой метки нет вовсе.
    """
    search = read_search(payload)
    page = read_page(payload, default_limit=subject.page_limit)

    async def run() -> dict:
        async with hub.session_factory() as session:
            rows, has_more = await subject.picker.rows(
                session,
                search=search,
                limit=page.limit,
                offset=page.offset,
                **subject.listing,
            )
        return {
            "search": search or "",
            subject.picker.key: [subject.picker.row_to_dict(row) for row in rows],
            "has_more": has_more,
        }

    return reply(hub.runner, run())


def vacancies_of(hub, subject: CardSubject, payload: dict) -> dict:
    """Короткий список вакансий предмета — для его карточки."""
    entity_id, refused = asked_id(
        payload, subject.id_key, f"{subject.domain}.vacancies"
    )
    if refused is not None:
        return refused

    async def run() -> dict:
        async with hub.session_factory() as session:
            rows = await subject.mini_vacancies(session, entity_id)
        return {
            subject.id_key: entity_id,
            "vacancies": [_vacancy_mini_row_to_dict(row) for row in rows],
        }

    return reply(hub.runner, run())


def merge_candidates(hub, subject: CardSubject, payload: dict) -> dict:
    """Кандидаты, в которых можно влить эту карточку."""
    try:
        absorbed_id = int(payload["absorbed_id"])
        search = text_or_none(payload.get("search"))
    except BAD_PAYLOAD as e:
        return bad_fields(f"{subject.domain}.merge_picker", e)

    async def run() -> dict:
        async with hub.session_factory() as session:
            return await merge_picker(session, subject.picker, absorbed_id, search)

    return reply(hub.runner, run())


def merge_into(hub, subject: CardSubject, payload: dict) -> dict:
    """Влить поглощаемую карточку в оставшуюся.

    Слияние с самой собой отбивается здесь, а не текстом репозитория: тот
    отвечает латиницей с двумя номерами, и делать человеку с такой фразой
    нечего. Остальные его отказы значат «одной из карточек уже нет» — их и
    объясняем словом предмета.
    """
    try:
        absorbed_id = int(payload["absorbed_id"])
        survivor_id = int(payload["survivor_id"])
    except BAD_PAYLOAD as e:
        return bad_fields(f"{subject.domain}.merge", e)

    async def run() -> dict:
        if absorbed_id == survivor_id:
            raise Denied(
                MERGE_INTO_SELF,
                absorbed_id=absorbed_id,
                action=subject.merge_action,
            )
        try:
            async with hub.session_factory() as session:
                async with session.begin():
                    await subject.merge_row(
                        session, absorbed_id=absorbed_id, survivor_id=survivor_id
                    )
        except ValueError:
            # Слово человеку — своё, а подлинная беда остаётся здесь: сегодня
            # репозиторий роняет это только на пропавшей карточке, но
            # следующий его `ValueError` стал бы ложным «не найден» без следа.
            logger.exception("%s: слить не вышло", subject.merge_action)
            raise Denied(
                subject.missing,
                absorbed_id=absorbed_id,
                action=subject.merge_action,
            )
        _tell(hub, subject)
        return {
            "action": subject.merge_action,
            "absorbed_id": absorbed_id,
            "survivor_id": survivor_id,
        }

    return reply(hub.runner, run())


def delete_card(hub, subject: CardSubject, entity_id: int) -> dict:
    """Снести карточку и сказать окну, что списки устарели.

    Номер приходит доводом, а не нагрузкой: обе кнопки сноса зовут мост числом.
    """
    return reply(hub.runner, _deleting(hub, subject, entity_id))


def create_card(hub, subject: CardSubject, payload: dict) -> dict:
    """Завести карточку по форме окна и назвать её номер.

    Само заведение общее с подборщиком при вакансии — там ту же форму
    открывают из карточки вакансии, — а здесь только дорога до него. Имя
    действия уходит в отказ полем: по нему окно понимает, какую форму держать
    открытой, и без него человек терял бы набранное.
    """
    try:
        fields = subject.read_fields(payload)
    except BAD_PAYLOAD as e:
        return bad_fields(f"{subject.domain}.create", e)

    async def run() -> dict:
        async with hub.session_factory() as session:
            created_id = await subject.create_row(
                session, fields, action=subject.create_action
            )
        return {"action": subject.create_action, "created_id": created_id}

    return reply(hub.runner, run())


async def _deleting(hub, subject: CardSubject, entity_id: int) -> dict:
    """Снос строки: пропажу — словом предмета, исход — вестями."""
    async with hub.session_factory() as session:
        if not await subject.delete_row(session, entity_id):
            raise Denied(
                subject.missing,
                action=subject.delete_action,
                **{subject.id_key: entity_id},
            )
        await session.commit()
    _tell(hub, subject)
    return {"action": subject.delete_action, subject.id_key: entity_id}


def asked_update(payload: dict, subject: CardSubject) -> tuple:
    """Номер предмета и присланные поля, а при негодном — готовый отказ окну.

    Голова правки у карточек общая: прочитать номер и отобрать присланные поля.
    Хвосты у них разъезжаются честно — компанию ловит занятое имя, человека
    негодный ник, — и потому здесь только голова.

    Пропущенный ключ значит «не трогать»: пустой набор и есть «правки нет», а
    что на неё ответить, решает зовущий — слова у карточек свои.
    """
    entity_id, refused = asked_id(
        payload, subject.id_key, f"{subject.domain}.update"
    )
    if refused is not None:
        return None, None, refused
    fields = {key: payload[key] for key in subject.update_fields if key in payload}
    return entity_id, fields, None


def _tell(hub, subject: CardSubject) -> None:
    """Разослать вести, которые слияние и снос делают устаревшими.

    Обе кнопки меняют одно и то же: перечень строк и числа под ними. Пока вести
    были написаны в самих кнопках, их забывали — у компании их не было вовсе, и
    после слияния соседние экраны показывали вчерашние числа до перезапуска.
    """
    for kind in subject.news:
        hub.events.add(kind)
