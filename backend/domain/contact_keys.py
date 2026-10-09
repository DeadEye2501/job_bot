"""Контакт вакансии: его вид — почта, телефон, ссылка — и нормальная форма, по которой два написания признаются одним."""

import re
from urllib.parse import parse_qsl, urlencode

from backend.domain.hosts import address_parts

# Почта и телефон, без якорей. По ним же разбор поста ищет адрес внутри строки
# (`backend/llm/vacancy.py`): что считать почтой и телефоном, решает одно правило.
EMAIL_PATTERN = r"[^\s@]+@[^\s@]+\.[a-zA-Z]{2,}"
PHONE_PATTERN = r"\+?\d[\d\s()-]{7,}\d"

_SCHEMES = ("mailto:", "tel:")
_ADDRESS_RE = re.compile(EMAIL_PATTERN)
_PHONE_RE = re.compile(PHONE_PATTERN)
_ARRIVAL_MARKS = ("utm_",)
_ARRIVAL_PARAMS = frozenset({"from"})


def contact_key(value: str) -> str:
    """Почта — без регистра и `mailto:`, телефон — одни цифры, ссылка — хост по
    правилу `normalize_host`, путь без косой черты в конце, без меток прихода.

    Остальное — текстом без лишних пробелов. Ссылкой считается только слитное
    написание с точкой в хосте: иначе подпись перед двоеточием («Почта: …»)
    стала бы хостом, и все контакты за ней получили бы один ключ.
    """
    text = _plain(value)
    if _ADDRESS_RE.fullmatch(text):
        return text
    if _PHONE_RE.fullmatch(text):
        return re.sub(r"\D", "", text)
    return _link_key(text) if _linkish(text) else text


def is_address(value: str) -> bool:
    """Почтовый адрес — по тому же правилу, что у ключа контакта."""
    return bool(_ADDRESS_RE.fullmatch(_plain(value)))


def is_phone(value: str) -> bool:
    """Телефон — по тому же правилу, что у ключа контакта."""
    return bool(_PHONE_RE.fullmatch(_plain(value)))


def is_link(value: str) -> bool:
    """Ссылка — по тому же правилу, что у ключа контакта: не почта, не телефон,
    слитное написание с точкой в хосте."""
    text = _plain(value)
    if _ADDRESS_RE.fullmatch(text) or _PHONE_RE.fullmatch(text):
        return False
    return _linkish(text)


def _linkish(text: str) -> bool:
    return bool(text) and " " not in text and "." in address_parts(text).host


def _plain(value: str) -> str:
    """Без регистра, лишних пробелов и схемы `mailto:` / `tel:`."""
    text = " ".join(value.lower().split())
    for scheme in _SCHEMES:
        text = text.removeprefix(scheme)
    return text


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
