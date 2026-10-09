"""Что считать одним контактом вакансии: перечень делится на контакты, а два
написания одного контакта признаются одним по нормальной форме."""

import re
from urllib.parse import parse_qsl, urlencode

from backend.domain.hosts import address_parts

# Почта, телефон и домен, без якорей. Ключ узнаёт по ним написание целиком, а
# поиск адреса внутри строки — его наличие: что считать адресом, решает одно
# правило.
EMAIL_PATTERN = r"[^\s@]+@[^\s@]+\.[a-zA-Z]{2,}"
PHONE_PATTERN = r"\+?\d[\d\s()-]{7,}\d"
DOMAIN_PATTERN = r"(?:www\.)?[a-zA-Z0-9-]+\.[a-zA-Z]{2,}"

# Адрес внутри строки — почта, ссылка целиком, домен или телефон. Строка без
# него не контакт, а подпись кнопки («Откликнуться») или указание словами
# («пишите в комментарии»): откликаться по ней некуда.
CONTACT_ADDRESS_RE = re.compile(
    rf"""
      {EMAIL_PATTERN}                                   # почта
    | https?://\S+                                      # ссылка целиком
    | {DOMAIN_PATTERN}(?:/\S*)?                         # домен
    | {PHONE_PATTERN}                                   # телефон
    """,
    re.VERBOSE,
)

_SCHEMES = ("mailto:", "tel:")
_ADDRESS_RE = re.compile(EMAIL_PATTERN)
_PHONE_RE = re.compile(PHONE_PATTERN)
_ARRIVAL_MARKS = ("utm_",)
_ARRIVAL_PARAMS = frozenset({"from"})
_LIST_SEPARATOR = re.compile(r",\s+")


def split_contacts(value: str) -> list[str]:
    """Контакты из строки, где их перечислили через запятую, — каждый отдельно.

    Записанный одной строкой перечень не узнаётся ни по одному из своих
    адресов: ключ у него один на всю строку.

    Делит только запятая с пробелом за ней: в пути ссылки запятая бывает
    частью адреса, и разрезанная там ссылка никуда бы не вела. Кусок без адреса
    («в теме укажите вакансию», «доб. 12») — продолжение соседнего контакта, а
    не контакт; строка, где адреса нет вовсе, контактов не даёт.
    """
    contacts: list[str] = []
    lead = ""
    for part in filter(None, (p.strip() for p in _LIST_SEPARATOR.split(value))):
        if CONTACT_ADDRESS_RE.search(part) is not None:
            contacts.append(lead + part)
            lead = ""
        elif contacts:
            contacts[-1] += f", {part}"
        else:
            lead += f"{part}, "
    return contacts


def contact_key(value: str) -> str:
    """Почта — без регистра и `mailto:`, телефон — одни цифры, ссылка — хост по
    правилу `normalize_host`, путь без косой черты в конце, без меток прихода.

    Остальное — текстом без лишних пробелов. Ссылкой считается только слитное
    написание с точкой в хосте: иначе подпись перед двоеточием («Почта: …»)
    стала бы хостом, и все контакты за ней получили бы один ключ.
    """
    text = " ".join(value.lower().split())
    for scheme in _SCHEMES:
        text = text.removeprefix(scheme)
    if _ADDRESS_RE.fullmatch(text):
        return text
    if _PHONE_RE.fullmatch(text):
        return re.sub(r"\D", "", text)
    if " " in text or "." not in address_parts(text).host:
        return text
    return _link_key(text)


def _link_key(text: str) -> str:
    parts = address_parts(text)
    kept = [
        (name, value)
        for name, value in parse_qsl(parts.query, keep_blank_values=True)
        if name not in _ARRIVAL_PARAMS and not name.startswith(_ARRIVAL_MARKS)
    ]
    path = f"/{parts.path}" if parts.path else ""
    query = f"?{urlencode(kept)}" if kept else ""
    fragment = f"#{parts.fragment}" if parts.fragment else ""
    return parts.host + path + query + fragment
