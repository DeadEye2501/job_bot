"""Компания как запись в контактах: найти, показать, поправить, убрать."""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError

from backend.incoming import int_or_none, text_or_none
from backend.repository import (
    companies_card,
    companies_list,
    hr_list,
    vacancies_mini,
)
from client.bridge.answer import Denied, bad_fields, denied, reply
from client.bridge.hub import Hub
from client.bridge.mark import COMPANY_MARK, mark, unmark
from client.bridge.page import read_page
from client.bridge.pickers import COMPANY_PICKER, merge_picker
from client.bridge.refusals import (
    COMPANY_EXISTS,
    NAME_REQUIRED,
    NOTHING_TO_UPDATE,
    NO_COMPANY,
)
from client.bridge.wire import (
    _company_picker_row_to_dict,
    _hr_mini_row_to_dict,
    _vacancy_mini_row_to_dict,
)
from client.form_payloads import read_company_spellings, read_new_company_fields


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
    try:
        async with session.begin():
            created_id = (await companies_card.create_company(session, **fields)).id
    except IntegrityError:
        raise Denied(COMPANY_EXISTS.format(name=name), **echo)
    return created_id


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

        Нагрузка та же, что у перечня людей: поиск, потолок со сдвигом, режим
        показа и порядковый знак. Знак уезжает эхом — по нему окно отбрасывает
        ответ, устаревший, пока менялись поиск или прокрутка.
        """
        # Не-объект сводится к пустоте, а не роняет разбор: поиск — дело окна,
        # и испорченная нагрузка не должна отнимать у человека весь перечень.
        payload = payload if isinstance(payload, dict) else {}
        search = text_or_none(payload.get("search"))
        page = read_page(payload, default_limit=50)

        async def run() -> dict:
            async with self._hub.session_factory() as session:
                rows, has_more = await companies_list.list_companies_with_counts(
                    session, search=search, limit=page.limit, offset=page.offset,
                )
            return {
                "search": search or "",
                "companies": [_company_picker_row_to_dict(r) for r in rows],
                "has_more": has_more,
                "mode": page.mode,
                "offset": page.offset,
                "epoch": page.epoch,
            }

        return reply(self._hub.runner, run())

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
                "vacancy_count": detail.vacancy_count,
                "hr_count": detail.hr_count,
                "blacklist_value": detail.blacklist_value,
            }

        return reply(self._hub.runner, run())

    def vacancies(self, payload: dict) -> dict:
        """Короткий список вакансий этой компании — для её карточки.

        Нагрузка: `{company_id, epoch}`. Номер отсеивает ответ про другую
        выбранную, порядковый знак — про ту же самую, спрошенную дважды подряд.
        Оба уезжают обратно эхом, устаревшее окно отбрасывает.
        """
        try:
            company_id = int(payload["company_id"])
            epoch = int_or_none(payload.get("epoch"))
        except (ValueError, TypeError, KeyError) as e:
            return bad_fields("companies.vacancies", e)

        async def run() -> dict:
            async with self._hub.session_factory() as session:
                rows = await vacancies_mini.list_vacancies_for_company(
                    session, company_id
                )
            return {
                "company_id": company_id,
                "epoch": epoch,
                "vacancies": [_vacancy_mini_row_to_dict(v) for v in rows],
            }

        return reply(self._hub.runner, run())

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
        try:
            absorbed_id = int(payload["absorbed_id"])
            search = text_or_none(payload.get("search"))
        except (ValueError, TypeError, KeyError) as e:
            return bad_fields("companies.merge_picker", e)

        async def run() -> dict:
            async with self._hub.session_factory() as session:
                return await merge_picker(session, COMPANY_PICKER, absorbed_id, search)

        return reply(self._hub.runner, run())

    def merge(self, payload: dict) -> dict:
        """Влить поглощаемую карточку в оставшуюся.

        Вакансии переезжают на оставшуюся, а прежнее имя остаётся у неё
        написанием: оно продолжает приходить в новых объявлениях, и потеряй его
        карточка — следующая вакансия завела бы компанию заново.
        """
        try:
            absorbed_id = int(payload["absorbed_id"])
            survivor_id = int(payload["survivor_id"])
        except (ValueError, TypeError, KeyError) as e:
            return bad_fields("companies.merge", e)

        async def run() -> dict:
            try:
                async with self._hub.session_factory() as session:
                    async with session.begin():
                        await companies_card.merge_company(
                            session,
                            absorbed_id=absorbed_id,
                            survivor_id=survivor_id,
                        )
            except ValueError as e:
                raise Denied(str(e), absorbed_id=absorbed_id, action="merge_company")
            return {
                "action": "merge_company",
                "absorbed_id": absorbed_id,
                "survivor_id": survivor_id,
            }

        return reply(self._hub.runner, run())

    def create(self, payload: dict) -> dict:
        """Завести компанию из окна «Добавить компанию».

        Номер заведённой едет ответом, чтобы окно подсветило новую строку.
        Само заведение — общее с подборщиком при вакансии.
        """
        try:
            fields = read_new_company_fields(payload)
        # `AttributeError` — про не-объект в нагрузке: помощник читает её
        # ключами, и спотыкается он до мотора, мимо конверта.
        except (AttributeError, ValueError, TypeError) as e:
            return bad_fields("companies.create", e)

        async def run() -> dict:
            async with self._hub.session_factory() as session:
                created_id = await create_company_row(
                    session, fields, action="create_company"
                )
            return {"action": "create_company", "created_id": created_id}

        return reply(self._hub.runner, run())

    def update(self, payload: dict) -> dict:
        """Поправить одно или несколько полей карточки.

        Пропущенный ключ значит «не трогать». Написания приходят то строкой
        через запятую, то готовым списком; всё прочее отбивается до базы —
        молчаливое приведение стёрло бы их разом.
        """
        try:
            company_id = int(payload["company_id"])
        except (ValueError, TypeError, KeyError) as e:
            return bad_fields("companies.update", e)

        kwargs = {
            key: payload[key]
            for key in ("name", "website", "notes")
            if key in payload
        }
        if "aliases" in payload:
            raw = payload["aliases"]
            if not isinstance(raw, (str, list)):
                return denied("aliases должен быть list или строка через запятую.")
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
        if not saved:
            raise Denied(
                "Компания не найдена или название пустое.",
                company_id=company_id, action="update_company",
            )
        return {
            "action": "update_company",
            "company_id": company_id,
            "fields": list(kwargs.keys()),
        }

    def delete(self, company_id: int) -> dict:
        """Убрать карточку компании (`companies_card.delete_company`)."""

        async def run() -> dict:
            async with self._hub.session_factory() as session:
                if not await companies_card.delete_company(session, company_id):
                    raise Denied(
                        NO_COMPANY, company_id=company_id, action="delete_company"
                    )
                await session.commit()
            return {"action": "delete_company", "company_id": company_id}

        return reply(self._hub.runner, run())

    def block(self, company_id: int) -> dict:
        """Занести компанию в чёрный список.

        Написание — имя компании: другого значения у неё нет, и именно его
        сверяет заслон отправки. Повторное нажатие второй записи не заводит:
        погашенная оживает, живая остаётся как есть. Про это говорят два поля:
        `existed` — «запись уже была», `was_inactive` — «была погашена и
        ожила»; по второму окно и различает эти два случая. Карточку это не
        сносит: снос — отдельная кнопка.
        """

        async def run() -> dict:
            async with self._hub.session_factory() as session:
                marked = await mark(session, COMPANY_MARK, company_id)
            self._hub.events.add("contacts_lists_changed")
            return marked

        return reply(self._hub.runner, run())

    def unblock(self, company_id: int) -> dict:
        """Убрать компанию из чёрного списка.

        Запись гасится, а не сносится: экран списка держит погашенные строки
        видимыми, с выключенным тумблером, — этого от кнопки «убрать» здесь и
        ждут.
        """

        async def run() -> dict:
            async with self._hub.session_factory() as session:
                unmarked = await unmark(session, COMPANY_MARK, company_id)
            self._hub.events.add("contacts_lists_changed")
            return unmarked

        return reply(self._hub.runner, run())
