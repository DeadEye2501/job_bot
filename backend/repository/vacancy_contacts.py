"""Контакты вакансии — всё, чем она указывает вовне, кроме Telegram-HR.

Адрес страницы вакансии стоит в той же выборке, что и контакты (`vacancy_addresses`):
сверке с отсевом сайтов он такой же адрес, как ссылка в контактах.
"""

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.contact_keys import contact_key
from backend.models import ContactAddedBy, Vacancy, VacancyContact


async def replace_parsed_contacts(
    session: AsyncSession, vacancy_id: int, values: list[str]
) -> None:
    """Заменить найденное разбором тем, что разбор нашёл сейчас.

    Строки агента и человека не трогаются. Найденное, которое уже есть под
    тем же ключом, второй строкой не заводится.
    """
    keys = [key for key in map(contact_key, values) if key]
    stale = delete(VacancyContact).where(
        VacancyContact.vacancy_id == vacancy_id,
        VacancyContact.added_by == ContactAddedBy.PARSE,
    )
    if keys:
        stale = stale.where(VacancyContact.match_key.not_in(keys))
    await session.execute(stale)
    for value in values:
        await add_contact(session, vacancy_id, value, ContactAddedBy.PARSE)


async def add_contact(
    session: AsyncSession, vacancy_id: int, value: str, added_by: ContactAddedBy
) -> None:
    """Завести контакт вакансии.

    Одна запись на всех, кто находит контакты, — кто нашёл, говорит `added_by`.
    Пустой ключ строкой не ложится, а контакт, уже известный под тем же ключом,
    второй строкой не заводится. Если прежняя строка — находка разбора, она
    переходит к тому, кто подтвердил контакт: иначе следующий разбор её бы стёр.
    """
    value = value.strip()
    key = contact_key(value)
    if not key:
        return
    known = await _contact_row(session, vacancy_id, key)
    if known is None:
        session.add(VacancyContact(
            vacancy_id=vacancy_id, value=value, match_key=key, added_by=added_by,
        ))
    elif known.added_by == ContactAddedBy.PARSE:
        known.added_by = added_by


async def _contact_row(
    session: AsyncSession, vacancy_id: int, key: str
) -> VacancyContact | None:
    return await session.scalar(
        select(VacancyContact).where(
            VacancyContact.vacancy_id == vacancy_id,
            VacancyContact.match_key == key,
        )
    )


async def list_contacts(session: AsyncSession, vacancy_id: int) -> list[VacancyContact]:
    """Контакты вакансии в порядке заведения."""
    return list((await session.scalars(
        select(VacancyContact)
        .where(VacancyContact.vacancy_id == vacancy_id)
        .order_by(VacancyContact.id)
    )).all())


async def contact_values(session: AsyncSession, vacancy_id: int) -> list[str]:
    """Значения контактов вакансии в порядке заведения."""
    return [contact.value for contact in await list_contacts(session, vacancy_id)]


async def vacancy_link(session: AsyncSession, vacancy_id: int) -> str | None:
    """Адрес страницы вакансии — тот, что открывает её карточка."""
    return await session.scalar(select(Vacancy.source_url).where(Vacancy.id == vacancy_id))


async def vacancy_addresses(session: AsyncSession, vacancy_id: int) -> list[str]:
    """Адрес страницы вакансии и все её контакты — то, чем она указывает вовне."""
    source_url = await vacancy_link(session, vacancy_id)
    return [address for address in (source_url, *await contact_values(session, vacancy_id)) if address]


async def delete_contact(session: AsyncSession, contact_id: int) -> int | None:
    """Удалить контакт. Ответ — номер его вакансии, или пусто, если контакта нет."""
    contact = await session.get(VacancyContact, contact_id)
    if contact is None:
        return None
    await session.delete(contact)
    await session.flush()
    return contact.vacancy_id
