"""Привязка вакансии к человеку и к компании: подборщики и их правки."""

from __future__ import annotations

from backend.models import Vacancy
from backend.incoming import text_or_none
from backend.repository import vacancies_card
from client.bridge.answer import Denied, bad_fields, reply
from client.bridge.companies import create_company_row
from client.bridge.hr import create_hr_row
from client.bridge.refusals import NO_VACANCY
from client.bridge.pickers import COMPANY_PICKER, HR_PICKER, link_picker
from client.form_payloads import read_new_company_fields, read_new_hr_fields


_CREATING = {
    "create_hr": (HR_PICKER, read_new_hr_fields, create_hr_row),
    "create_company": (COMPANY_PICKER, read_new_company_fields, create_company_row),
}
"""Чем заведение человека отличается от заведения компании.

Тремя вещами и больше ничем: чтением формы, объявлением, которое пишет запись, и
подборщиком, чей список надо перечитать. Ключ — имя метода поверхности: он же
едет в жалобу журнала, и второе имя для того же места разошлось бы с первым.
"""


class VacancyLinks:
    """Кого и что окно привязывает к вакансии, и как оно их ищет.

    Собирающий обязан держать `_hub`: из него берутся мотор и сессии.
    """

    def hr_picker(self, payload: dict) -> dict:
        """Список людей для окна «Связать с HR».

        Привязанный сейчас возвращается эхом, чтобы окно отметило строку не
        спрашивая второй раз. Поиск отбирает база — с приведением регистра,
        годным и для кириллицы.
        """
        try:
            vacancy_id = int(payload["vacancy_id"])
            search = text_or_none(payload.get("search"))
        except (ValueError, TypeError, KeyError) as e:
            return bad_fields("hr_picker", e)

        return reply(self._hub.runner, self._picker(HR_PICKER, vacancy_id, search))

    def company_picker(self, payload: dict) -> dict:
        """Список компаний для окна «Связать с компанией»."""
        try:
            vacancy_id = int(payload["vacancy_id"])
            search = text_or_none(payload.get("search"))
        except (ValueError, TypeError, KeyError) as e:
            return bad_fields("company_picker", e)

        return reply(self._hub.runner, self._picker(COMPANY_PICKER, vacancy_id, search))

    def link_hr(self, payload: dict) -> dict:
        """Привязать человека к вакансии или снять привязку.

        Пустой номер значит «отвязать». Ответ помечен тем же действием, что и
        остальные кнопки карточки: окно перерисовывает её одним обработчиком.
        """
        try:
            vacancy_id = int(payload["vacancy_id"])
            raw = payload.get("hr_id")
            hr_id = int(raw) if raw is not None else None
        except (ValueError, TypeError, KeyError) as e:
            return bad_fields("link_hr", e)

        async def run() -> dict:
            await self._linked(
                vacancies_card.set_vacancy_hr, vacancy_id, hr_id, "link_hr"
            )
            return {"vacancy_id": vacancy_id, "hr_id": hr_id, "action": "link_hr"}

        return reply(self._hub.runner, run())

    def link_company(self, payload: dict) -> dict:
        """Привязать компанию к вакансии или снять привязку."""
        try:
            vacancy_id = int(payload["vacancy_id"])
            raw = payload.get("company_id")
            company_id = int(raw) if raw is not None else None
        except (ValueError, TypeError, KeyError) as e:
            return bad_fields("link_company", e)

        async def run() -> dict:
            await self._linked(
                vacancies_card.set_vacancy_company,
                vacancy_id,
                company_id,
                "link_company",
            )
            return {
                "vacancy_id": vacancy_id,
                "company_id": company_id,
                "action": "link_company",
            }

        return reply(self._hub.runner, run())

    def create_hr(self, payload: dict) -> dict:
        """Завести человека прямо из подборщика и вернуть обновлённый список.

        Номер заведённого едет ответом, чтобы окно подсветило строку; сама
        привязка по-прежнему за кнопкой «Связать».
        """
        return self._created("create_hr", payload)

    def create_company(self, payload: dict) -> dict:
        """Завести компанию прямо из подборщика и вернуть обновлённый список."""
        return self._created("create_company", payload)

    def _created(self, slot: str, payload: dict) -> dict:
        """Завести запись из подборщика и отдать список, в котором она уже есть.

        Список и номер едут одним ответом нарочно: приди номер без списка,
        окно подсветило бы строку, которой в нём ещё нет.

        Человек и компания заводятся одинаково — разнятся у них чтение формы,
        объявление, которое пишет запись, и подборщик, чей список надо
        перечитать. Всё три названы в `_CREATING`, а не доводами: доводами это
        четыре параметра на метод из шести строк.
        """
        subject, read_fields, create_row = _CREATING[slot]
        try:
            vacancy_id = int(payload["vacancy_id"])
            fields = read_fields(payload)
            search = text_or_none(payload.get("search"))
        except (ValueError, TypeError, KeyError) as e:
            return bad_fields(slot, e)

        async def run() -> dict:
            async with self._hub.session_factory() as session:
                created_id = await create_row(session, fields, vacancy_id=vacancy_id)
                listed = await self._listing(session, subject, vacancy_id, search)
            return {**listed, "created_id": created_id}

        return reply(self._hub.runner, run())

    async def _picker(self, kind, vacancy_id: int, search: str | None) -> dict:
        """Открыть подборщик: без вакансии открывать нечего."""
        async with self._hub.session_factory() as session:
            if await session.get(Vacancy, vacancy_id) is None:
                raise Denied(NO_VACANCY, vacancy_id=vacancy_id)
            return await self._listing(session, kind, vacancy_id, search)

    async def _listing(self, session, kind, vacancy_id: int, search: str | None) -> dict:
        """Список подборщика вместе с эхом вакансии, для которой он собран.

        Вакансии может уже не быть — её снесли в соседнем окне, пока здесь
        заводили человека. Отказывать поздно: запись легла, и показать список
        всё равно есть смысл; привязанного в нём тогда просто нет.
        """
        vacancy = await session.get(Vacancy, vacancy_id)
        return {
            "vacancy_id": vacancy_id,
            **await link_picker(session, kind, vacancy, search),
        }

    async def _linked(self, setting, vacancy_id: int, other_id: int | None, action: str):
        """Привязка одной стороны: отказ базы и пропажу вакансии — словами."""
        try:
            async with self._hub.session_factory() as session:
                async with session.begin():
                    linked = await setting(session, vacancy_id, other_id)
        except ValueError as e:
            raise Denied(str(e), vacancy_id=vacancy_id, action=action)
        if not linked:
            raise Denied(NO_VACANCY, vacancy_id=vacancy_id, action=action)
