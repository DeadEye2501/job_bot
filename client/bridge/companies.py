"""Компания как запись в контактах: найти, показать, поправить, убрать."""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError

from backend.repository import companies_card, hr_list, vacancies_mini
from client.bridge.answer import Denied, denied, reply
from client.bridge.cards import (
    CardSubject,
    asked_update,
    create_card,
    created_or_taken,
    delete_card,
    listed,
    merge_candidates,
    merge_into,
    vacancies_of,
)
from client.bridge.hub import Hub
from client.bridge.mark import COMPANY_MARK, marked, unmarked
from client.bridge.pickers import COMPANY_PICKER
from client.bridge.refusals import (
    COMPANY_EXISTS,
    NAME_REQUIRED,
    NOTHING_TO_UPDATE,
    NO_COMPANY,
    SPELLINGS_SHAPE,
)
from client.bridge.wire import _hr_mini_row_to_dict
from client.bridge.form_payloads import read_company_spellings, read_new_company_fields


async def create_company_row(session, fields: dict, **echo) -> int:
    """Завести компанию по прочитанной форме окна и назвать её номер.

    Форма одна, а окон два: «Добавить компанию» в контактах и заведение на ходу
    из подборщика при вакансии. Правила у них общие — без названия карточку не
    найти потом ничем, а занятое имя объясняется словами, а не отказом базы:
    компании с одинаковым именем считаются одной, и заводящий вторую должен
    узнать про первую.

    Перехват здесь один, и это перехват из окна контактов. `ValueError` пустого
    названия, который ловил подборщик, недостижим: пустое отбивает заслон
    строкой выше, а другого повода бросить его у `create_company` нет.

    Поля отказа отдаёт зовущий: карточке нужно имя действия, подборщику — номер
    вакансии, из которой заводят.
    """
    name = fields["name"]
    if not name:
        raise Denied(NAME_REQUIRED, **echo)
    return await created_or_taken(
        session,
        lambda: companies_card.create_company(session, **fields),
        COMPANY_EXISTS.format(name=name),
        **echo,
    )


COMPANY_CARD = CardSubject(
    picker=COMPANY_PICKER,
    id_key="company_id",
    missing=NO_COMPANY,
    domain="companies",
    page_limit=50,
    listing={},
    read_fields=read_new_company_fields,
    update_fields=("name", "website", "notes"),
    mini_vacancies=vacancies_mini.list_vacancies_for_company,
    merge_row=companies_card.merge_company,
    delete_row=companies_card.delete_company,
    create_row=create_company_row,
    merge_action="merge_company",
    delete_action="delete_company",
    create_action="create_company",
    news=("contacts_lists_changed",),
)
"""Компания, какой её знает общая карточка контакта.

Весть одна, а у человека их две: счёт непрочитанного двигает только он —
переписку сносят и переносят вместе с ним. Прежде у компании не было ни одной,
и после слияния соседние экраны показывали вчерашние числа до перезапуска.
"""


class Companies:
    """Компания как запись в контактах: найти, показать, поправить, убрать.

    Заслон и его снятие кладут в очередь весть о том, что списки контактов
    устарели: отметка отсева запечена в строках людей, компаний и каналов, и
    без вести соседние экраны показывали бы компанию незаслонённой.
    """

    def __init__(self, hub: Hub) -> None:
        self._hub = hub

    def list(self, payload: dict | None = None) -> dict:
        """Страница перечня компаний.

        Нагрузка та же, что у перечня людей: поиск и потолок со сдвигом.
        """
        return listed(self._hub, COMPANY_CARD, payload)

    def detail(self, company_id: int) -> dict:
        """Карточка одной компании целиком.

        Номер едет обратно в отказе: по нему окно убирает строку, за которой
        компании уже нет, — перечень, из которого её открыли, мог устареть.
        """

        async def run() -> dict:
            async with self._hub.session_factory() as session:
                detail = await companies_card.get_company_detail(session, company_id)
            if detail is None:
                raise Denied(NO_COMPANY, company_id=company_id)
            return {
                "company_id": detail.company.id,
                "name": detail.company.name,
                "website": detail.company.website,
                "aliases": list(detail.company.aliases or []),
                "notes": detail.company.notes,
                "blacklist_value": detail.blacklist_value,
            }

        return reply(self._hub.runner, run())

    def vacancies(self, payload: dict) -> dict:
        """Короткий список вакансий этой компании — для её карточки.

        Нагрузка: `{company_id}`.
        """
        return vacancies_of(self._hub, COMPANY_CARD, payload)

    def people(self, company_id: int) -> dict:
        """Люди, у которых есть хоть одна вакансия в этой компании.

        Счёт вакансий у каждого — только по этой компании, а не по всем: в её
        карточке общее число говорило бы не о ней.
        """

        async def run() -> dict:
            async with self._hub.session_factory() as session:
                rows = await hr_list.list_hrs_for_company(session, company_id)
            return {
                "company_id": company_id,
                "hrs": [_hr_mini_row_to_dict(hr, count) for hr, count in rows],
            }

        return reply(self._hub.runner, run())

    def merge_picker(self, payload: dict) -> dict:
        """Кандидаты, в которых можно влить эту карточку.

        Строка та же, что у подборщика вакансий, за вычетом самой поглощаемой
        карточки.
        """
        return merge_candidates(self._hub, COMPANY_CARD, payload)

    def merge(self, payload: dict) -> dict:
        """Влить поглощаемую карточку в оставшуюся.

        Вакансии переезжают на оставшуюся, а прежнее имя остаётся у неё
        написанием: оно продолжает приходить в новых объявлениях, и потеряй его
        карточка — следующая вакансия завела бы компанию заново.
        """
        return merge_into(self._hub, COMPANY_CARD, payload)

    def create(self, payload: dict) -> dict:
        """Завести компанию из окна «Добавить компанию».

        Номер заведённой едет ответом, чтобы окно подсветило новую строку.
        Само заведение — общее с подборщиком при вакансии.
        """
        return create_card(self._hub, COMPANY_CARD, payload)

    def update(self, payload: dict) -> dict:
        """Поправить одно или несколько полей карточки.

        Пропущенный ключ значит «не трогать». Написания приходят то строкой
        через запятую, то готовым списком; всё прочее отбивается до базы —
        молчаливое приведение стёрло бы их разом.
        """
        company_id, kwargs, refused = asked_update(payload, COMPANY_CARD)
        if refused is not None:
            return refused
        if "aliases" in payload:
            raw = payload["aliases"]
            if not isinstance(raw, (str, list)):
                return denied(SPELLINGS_SHAPE, company_id=company_id)
            kwargs["aliases"] = read_company_spellings(raw)
        if not kwargs:
            return denied(NOTHING_TO_UPDATE, company_id=company_id)

        return reply(self._hub.runner, self._updated(company_id, kwargs))

    async def _updated(self, company_id: int, kwargs: dict) -> dict:
        """Записать прочитанные поля и назвать окну, какие из них поправлены.

        Занятое имя объясняется теми же словами, что и при заведении: руками
        сводя дубли, человек как раз и переименовывает одну компанию в другую.
        Уникальна у компании только колонка имени, поэтому иного повода для
        отказа базы здесь нет, и написанное в форме имя у отказа всегда есть.
        """
        async with self._hub.session_factory() as session:
            try:
                async with session.begin():
                    saved = await companies_card.update_company_fields(
                        session, company_id, **kwargs,
                    )
            except IntegrityError:
                raise Denied(
                    COMPANY_EXISTS.format(name=kwargs["name"]),
                    company_id=company_id, action="update_company",
                )
            except ValueError:
                # Пустое имя — не «компании нет»: правило живёт в репозитории,
                # а здесь только его перевод человеку. Прежде оба случая
                # приходили одной ложью, и фраза склеивала их в одно
                # предложение про оба сразу.
                raise Denied(
                    NAME_REQUIRED, company_id=company_id, action="update_company"
                )
        if not saved:
            raise Denied(
                NO_COMPANY, company_id=company_id, action="update_company"
            )
        return {
            "action": "update_company",
            "company_id": company_id,
            "fields": list(kwargs.keys()),
        }

    def delete(self, company_id: int) -> dict:
        """Убрать карточку компании (`companies_card.delete_company`)."""
        return delete_card(self._hub, COMPANY_CARD, company_id)

    def block(self, company_id: int) -> dict:
        """Занести компанию в чёрный список.

        Написание — имя компании: другого значения у неё нет, и именно его
        сверяет заслон отправки. Повторное нажатие второй записи не заводит:
        погашенная оживает, живая остаётся как есть. Про это говорят два поля:
        `existed` — «запись уже была», `was_inactive` — «была погашена и
        ожила»; по второму окно и различает эти два случая. Карточку это не
        сносит: снос — отдельная кнопка.
        """

        return reply(self._hub.runner, marked(self._hub, COMPANY_MARK, company_id))

    def unblock(self, company_id: int) -> dict:
        """Убрать компанию из чёрного списка.

        Запись гасится, а не сносится: экран списка держит погашенные строки
        видимыми, с выключенным тумблером, — этого от кнопки «убрать» здесь и
        ждут.
        """

        return reply(self._hub.runner, unmarked(self._hub, COMPANY_MARK, company_id))
