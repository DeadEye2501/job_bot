"""Привязка вакансии к человеку и к компании: подборщики и их правки."""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError

from backend.models import Vacancy
from backend.payloads import text_or_none
from backend.repository import companies_card, hr_identify, vacancies_card
from client.bridge.answer import Denied, bad_fields, denied, reply
from client.bridge.refusals import (
    COMPANY_EXISTS,
    IDENTITY_REQUIRED,
    NAME_REQUIRED,
    NO_VACANCY,
)
from client.bridge.pickers import COMPANY_PICKER, HR_PICKER, link_picker
from client.form_payloads import (
    hr_is_identified,
    read_new_company_fields,
    read_new_hr_fields,
)


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
        try:
            vacancy_id = int(payload["vacancy_id"])
            fields = read_new_hr_fields(payload)
            search = text_or_none(payload.get("search"))
        except (ValueError, TypeError, KeyError) as e:
            return bad_fields("create_hr", e)

        if not hr_is_identified(fields):
            return denied(IDENTITY_REQUIRED, vacancy_id=vacancy_id)

        async def run() -> dict:
            async with self._hub.session_factory() as session:
                async with session.begin():
                    created_id = (await hr_identify.create_hr(session, **fields)).id
                listed = await self._listing(session, HR_PICKER, vacancy_id, search)
            return {**listed, "created_id": created_id}

        return reply(self._hub.runner, run())

    def create_company(self, payload: dict) -> dict:
        """Завести компанию прямо из подборщика и вернуть обновлённый список."""
        try:
            vacancy_id = int(payload["vacancy_id"])
            fields = read_new_company_fields(payload)
            name = fields["name"]
            search = text_or_none(payload.get("search"))
        except (ValueError, TypeError, KeyError) as e:
            return bad_fields("create_company", e)

        if not name:
            return denied(NAME_REQUIRED, vacancy_id=vacancy_id)

        async def run() -> dict:
            try:
                async with self._hub.session_factory() as session:
                    async with session.begin():
                        created = await companies_card.create_company(session, **fields)
                        created_id = created.id
                    listed = await self._listing(
                        session, COMPANY_PICKER, vacancy_id, search
                    )
            except IntegrityError:
                raise Denied(COMPANY_EXISTS.format(name=name), vacancy_id=vacancy_id)
            except ValueError as e:
                raise Denied(str(e), vacancy_id=vacancy_id)
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
