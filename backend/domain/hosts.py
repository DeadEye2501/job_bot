"""Разбор адреса: нормальный хост, остаток, принадлежность сайту, номер страницы."""

from typing import NamedTuple
from urllib.parse import parse_qsl, urlsplit

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
    целиком. К пути добавляются параметры, похожие на номер (`_numbering`).
    """
    parts = address_parts(url)
    if not parts.host or not parts.path:
        return None
    # Регистр снимается с хоста и пути, но не с номера в параметре: `AbC` и
    # `abc` бывают разными вакансиями.
    numbering = _numbering(parts.query)
    if aggregator_host is None:
        return f"{parts.host}/{parts.path}".lower() + numbering
    return parts.path + numbering if host_owns(aggregator_host, parts.host) else None


def is_arrival_mark(name: str) -> bool:
    """Параметр адреса, который говорит, откуда пришли, а не на что смотрят.

    Метки рекламы, кликов и сессии. Имя ждётся в нижнем регистре.
    """
    return (name.startswith("utm") or name.endswith(("clid", "clkid"))
            or "sess" in name or name in {"sid", "from"})


def _numbering(query: str) -> str:
    """Параметры адреса, похожие на номер: с `id` в имени или с числом в значении.

    Остальные отбрасываются: метки прихода меняют адрес, а не вакансию. Метки
    кликов и сессии кончаются на `id` и бывают числами, поэтому отсеиваются
    раньше. Ошибка в сторону лишнего параметра дешева: повтор с другим номером
    ловит сверка по похожести текста. Ошибка в сторону потерянного сливает две
    вакансии в одну молча.
    """
    kept = []
    for name, value in parse_qsl(query):
        low = name.lower()
        if not is_arrival_mark(low) and ("id" in low or value.isdigit()):
            kept.append(f"{name}={value}")
    return "?" + "&".join(sorted(kept)) if kept else ""


def _without_scheme(url: str) -> str:
    """Адрес без схемы и косых черт перед хостом; регистр не трогается."""
    return ADDRESS_START_RE.sub("", url.strip()).lstrip("/")
