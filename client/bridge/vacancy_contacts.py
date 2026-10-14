"""Контакты вакансии, которые человек правит в карточке."""

from __future__ import annotations

from backend.domain.contact_keys import contact_key
from backend.models import ContactAddedBy
from backend.repository import vacancy_contacts
from backend.incoming import text_or_none
from client.bridge.answer import BAD_PAYLOAD, Denied, asked_id, bad_fields, denied, reply
from client.bridge.refusals import NO_ENTRY
from client.bridge.vacancy_links import require_vacancy
from client.bridge.wire import _contact


class VacancyContacts:
    """Добавление и удаление контакта; ответом — контакты вакансии целиком."""

    def add_contact(self, payload: dict) -> dict:
        try:
            vacancy_id = int(payload["vacancy_id"])
            value = text_or_none(payload.get("value"))
        except BAD_PAYLOAD as e:
            return bad_fields("add_contact", e)
        if value is None or not contact_key(value):
            return denied("Пустой контакт не добавить")

        async def run() -> dict:
            async with self._hub.session_factory() as session:
                async with session.begin():
                    await require_vacancy(session, vacancy_id)
                    await vacancy_contacts.add_contact(
                        session, vacancy_id, value, ContactAddedBy.USER
                    )
                    return await _contacts_of(session, vacancy_id)

        return reply(self._hub.runner, run())

    def delete_contact(self, payload: dict) -> dict:
        contact_id, refused = asked_id(payload, "contact_id", "delete_contact")
        if refused is not None:
            return refused

        async def run() -> dict:
            async with self._hub.session_factory() as session:
                async with session.begin():
                    vacancy_id = await vacancy_contacts.delete_contact(session, contact_id)
                    if vacancy_id is None:
                        raise Denied(NO_ENTRY, contact_id=contact_id)
                    return await _contacts_of(session, vacancy_id)

        return reply(self._hub.runner, run())


async def _contacts_of(session, vacancy_id: int) -> dict:
    rows = await vacancy_contacts.list_contacts(session, vacancy_id)
    return {"vacancy_id": vacancy_id, "contacts": [_contact(c) for c in rows]}
