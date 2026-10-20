"""Начало адреса: схема с косыми чертами перед хостом.

Отдельно от разбора хоста (`hosts`), потому что начало адреса нужно и хостам,
и ссылкам Telegram, и названиям компаний, а хосты сами разбирают ссылки
Telegram.
"""

import re

ADDRESS_START_RE = re.compile(r"^[a-z][a-z0-9+.\-]*://", re.IGNORECASE)


def without_scheme(url: str) -> str:
    """Адрес без схемы и косых черт перед хостом; регистр не трогается."""
    return ADDRESS_START_RE.sub("", url.strip()).lstrip("/")
