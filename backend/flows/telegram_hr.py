"""Telegram из разбора и находки — в HR вакансии и в её контакты.

Шаг между разбором и записью. Все записи Telegram — названный разбором HR,
прочие контакты разбора и записанное искателем со страницы — делятся вопросом к
Telegram на людей и прочих; что делать с ответом, решает
`domain/telegram_contacts.sorted_telegram`.

Не ответил Telegram и на повтор — человек за ником или канал, неизвестно, и шаг
не делается вовсе: записывается то, что нашёл разбор.
"""

import logging
from dataclasses import dataclass, field, replace

from backend.domain.telegram_contacts import TelegramContact, sorted_telegram, telegram_contacts
from backend.domain.telegram_identity import normalize_username
from backend.payloads import ParsedVacancy
from backend.repository.vacancy_contacts import agent_contact_values
from backend.telegram_lookup import fetch_telegram_avatar, find_person

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HrPick:
    """Что записать: разбор с выбранным HR и без людей в контактах, собеседник
    Telegram с картинкой и записи искателя, которые уходят из контактов."""

    parsed: ParsedVacancy | None
    user: object | None = None
    avatar: bytes | None = None
    dropped: list[str] = field(default_factory=list)


async def pick_hr(pipeline, vacancy_id: int, parsed: ParsedVacancy | None) -> HrPick:
    """Поделить Telegram вакансии на людей и прочих и выбрать HR.

    Идёт до сессии записи: вопросы к Telegram ждут сети, и в начатой сделке
    база всё это время не приняла бы ни одной записи.
    """
    if parsed is None:
        return HrPick(None)
    async with pipeline.session_factory() as session:
        found = await agent_contact_values(session, vacancy_id)
    people = await _people(pipeline.client, telegram_contacts(parsed.hr_contact, [*parsed.other_contacts, *found]))
    if people is None:
        return HrPick(parsed)
    result = sorted_telegram(parsed.hr_contact, parsed.other_contacts, found, set(people))
    user = people[normalize_username(result.hr_contact).lower()] if result.hr_contact else None
    return HrPick(
        replace(parsed, hr_contact=result.hr_contact, other_contacts=result.other_contacts),
        user,
        await fetch_telegram_avatar(pipeline.client, user) if user is not None else None,
        result.dropped,
    )


async def _people(client, contacts: list[TelegramContact]) -> dict[str, object] | None:
    """Люди среди записей: ник без регистра → собеседник Telegram; пусто — Telegram
    не ответил и на повтор."""
    people = {}
    for contact in contacts:
        if contact.username is None:
            continue
        user, trouble = await find_person(client, contact.username)
        if trouble is not None:
            user, trouble = await find_person(client, contact.username)
        if trouble is not None:
            logger.warning("Telegram не ответил о %r и на повтор: Telegram вакансии остаётся, "
                           "как нашёл разбор", contact.value)
            return None
        if user is not None:
            people[contact.username.lower()] = user
    return people
