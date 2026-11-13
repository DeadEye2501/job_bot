"""Telegram среди контактов вакансии: о ком спрашивать Telegram и кого из людей взять HR.

HR у вакансии один, и это человек. Прочий Telegram — канал, пост, группа, бот —
контакт, как почта и ссылка. Человек ли за ником, говорит только сам Telegram;
здесь решается то, что видно по записи, и что делать с ответом.
"""

from dataclasses import dataclass

from backend.domain.contact_keys import contact_key
from backend.domain.hosts import link_kind
from backend.domain.telegram_identity import normalize_username


@dataclass(frozen=True)
class TelegramContact:
    """Запись Telegram, как она пришла, и ник, о котором спрашивать Telegram.

    У поста ника нет: пост — не человек, и спрашивать о нём нечего.
    """

    value: str
    username: str | None


@dataclass(frozen=True)
class SortedTelegram:
    """Telegram вакансии после ответа: HR, контакты без людей и записи искателя,
    которые уходят из контактов — в HR или в отброшенные люди."""

    hr_contact: str | None
    other_contacts: list[str]
    dropped: list[str]


def telegram_contacts(named: str | None, values: list[str]) -> list[TelegramContact]:
    """Записи Telegram по порядку — названный HR, затем `values`, — каждая один раз.

    Названный HR — Telegram в любом написании, и голый ник тоже: так его
    отдаёт разбор. Среди прочих Telegram — `@ник`, ссылка на ник и пост; голое
    слово там — не ник. Один ник, записанный по-разному (`@anna`, `t.me/anna`), —
    одна запись, первая. Ссылка-приглашение и прочий Telegram без ника сюда не
    идут: о человеке за ними не спросить, и они остаются контактами.
    """
    first = [_named(named)] if named else []
    found: dict[str, TelegramContact] = {}
    for contact in [*first, *map(_telegram, values)]:
        if contact is not None:
            found.setdefault(_key(contact), contact)
    return list(found.values())


def sorted_telegram(named: str | None, others: list[str], found: list[str], people: set[str]) -> SortedTelegram:
    """Разложить Telegram вакансии по ответу Telegram.

    `named` — названный разбором HR, `others` — прочие контакты разбора, `found` —
    записанное искателем, `people` — ники людей без регистра. HR — названный,
    если он человек, иначе первый человек по порядку; прочие люди не идут никуда.
    Названный, оказавшийся не человеком, — контакт; голый ник пишется с `@`, иначе
    в карточке он читался бы простым словом. Один Telegram, записанный по-разному,
    ложится в контакты один раз.
    """
    contacts = telegram_contacts(named, [*others, *found])
    persons = [one for one in contacts if one.username and one.username.lower() in people]
    chosen = chosen_person(_named(named).username if named else None, [one.username for one in persons])
    hr = next((one.value for one in persons if one.username == chosen), None)
    left = [_written(named)] if named and not _is_person(_named(named), people) else []
    kept: dict[str, str] = {}
    for value in [*left, *others]:
        contact = _telegram(value)
        if not _is_person(contact, people):
            kept.setdefault(_key(contact) if contact else contact_key(value), value)
    return SortedTelegram(hr, list(kept.values()), [value for value in found if _is_person(_telegram(value), people)])


def chosen_person(named: str | None, people: list[str]) -> str | None:
    """Ник HR среди ников людей: названный разбором, если он человек, иначе первый."""
    if named is not None:
        for name in people:
            if name.lower() == named.lower():
                return name
    return people[0] if people else None


def _is_person(contact: TelegramContact | None, people: set[str]) -> bool:
    return contact is not None and contact.username is not None and contact.username.lower() in people


def _written(named: str) -> str:
    name = _named(named).username
    return f"@{name}" if name and _telegram(named) is None else named


def _named(value: str) -> TelegramContact:
    """Запись названного HR: разбор кладёт туда только годный ник (`llm/vacancy._contacts`)."""
    return _telegram(value) or TelegramContact(value, normalize_username(value))


def _telegram(value: str) -> TelegramContact | None:
    kind = link_kind(value)
    if kind == "post":
        return TelegramContact(value, None)
    if kind != "channel" and not value.startswith("@"):
        return None
    name = normalize_username(value)
    return TelegramContact(value, name) if name else None


def _key(contact: TelegramContact) -> str:
    return contact.username.lower() if contact.username else contact_key(contact.value)
