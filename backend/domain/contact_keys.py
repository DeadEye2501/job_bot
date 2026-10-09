"""Нормальная форма контакта вакансии, по которой два написания признаются одним."""

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
