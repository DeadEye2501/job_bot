"""Узнаёт ли вакансия свой контакт в чужом написании."""

from backend.repository.vacancy_contacts import has_contact
from tests.dbio import put
from tests.factories import vacancy_row
from tests.factories_aggregators import vacancy_contact_row


async def test_a_contact_is_known_in_any_spelling(session, session_factory):
    vacancy = vacancy_row()
    await put(session_factory, vacancy)
    await put(session_factory, vacancy_contact_row(vacancy.id, "hr@x.ru"))

    assert await has_contact(session, vacancy.id, " mailto:HR@X.ru ") is True
    assert await has_contact(session, vacancy.id, "other@x.ru") is False
