"""Разбор адреса: нормальный хост, остаток, принадлежность сайту, номер страницы."""

from typing import NamedTuple
from urllib.parse import urlsplit

from backend.domain.company_names import ADDRESS_START_RE


class AddressParts(NamedTuple):
    host: str
    path: str
    query: str
    fragment: str


def normalize_host(url: str | None) -> str:
    """Хост сайта без схемы / www. / порта / пути / query / fragment /
    завершающей точки. Пустая строка для None или невалидного URL.
    Полный host (а не registrable domain) — чтобы `pay.yandex.ru` ≠
    `yandex.ru` (subsidiary trap)."""
    if not url:
        return ""
    s = _without_scheme(url.lower())
    # Срезаем path / query / fragment ДО того, как лезть в port:
    # "sber.ru?utm=foo" без strip-а query превратился бы в host
    # "sber.ru?utm=foo" и сломал бы host-match.
    s = s.split("/", 1)[0]
    s = s.split("?", 1)[0]
    s = s.split("#", 1)[0]
    s = s.split(":", 1)[0]
    if s.startswith("www."):
        s = s[4:]
    # FQDN с завершающей точкой ("example.com.") — нормализуем к
    # "example.com", иначе host-match отказывает на пустяковом расхождении.
    s = s.rstrip(".")
    return s


def address_parts(url: str) -> AddressParts:
    """Адрес по частям: хост, путь без косых черт по краям, параметры и якорь.

    Хост даёт `normalize_host`, а не `urlsplit`: тот оставил бы порт,
    завершающую точку и регистр, и одна ссылка получила бы два хоста.
    """
    text = _without_scheme(url)
    try:
        parts = urlsplit("//" + text)
    except ValueError:
        # Непарную «[» urlsplit принимает за начало адреса IPv6 и бросает. Контакт
        # из текста вакансии бывает каким угодно, а запись разбора из-за него
        # падать не должна: путь — всё после хоста, как есть.
        return AddressParts(normalize_host(url), text.partition("/")[2].strip("/"), "", "")
    return AddressParts(
        normalize_host(url), parts.path.strip("/"), parts.query, parts.fragment
    )


def host_owns(host: str, link_host: str) -> bool:
    """Ссылка принадлежит сайту, если её хост равен его хосту или кончается на точку и его хост.

    Хвост берётся с точкой: `spb.hh.ru` — та же площадка, а `nothh.ru` — нет.
    """
    return link_host == host or link_host.endswith("." + host)


def source_key(url: str, aggregator_host: str | None) -> str | None:
    """Номер вакансии: у агрегатора — путь страницы, у поиска по сети — хост и путь.

    Сайты в сети разные, и одну страницу от другой отличает только адрес
    целиком. Номер в адресе у агрегатора, устроенного иначе, дописывается здесь.
    """
    parts = address_parts(url)
    if not parts.host or not parts.path:
        return None
    if aggregator_host is None:
        return f"{parts.host}/{parts.path}".lower()
    return parts.path if host_owns(aggregator_host, parts.host) else None


def _without_scheme(url: str) -> str:
    """Адрес без схемы и косых черт перед хостом; регистр не трогается."""
    return ADDRESS_START_RE.sub("", url.strip()).lstrip("/")
