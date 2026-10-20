"""Разбор адреса: нормальный хост, имя сайта, остаток, принадлежность сайту, номер страницы, род ссылки."""

import re
from typing import Literal, NamedTuple
from urllib.parse import parse_qsl, urlsplit

from backend.domain.address_start import without_scheme
from backend.domain.telegram_identity import (
    ARTICLE_URL_RE, TELEGRAM_HOSTS, TELEGRAM_LINK_HOSTS, TELEGRAPH_HOSTS, post_address,
)


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
    s = without_scheme(url.lower())
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
    text = without_scheme(url)
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


# Вторые уровни, под которыми зоны стран раздают имена сайтам: `example.co.uk`
# назван «example», а не «co». Перечнем общих слов, а не длиной метки: короткое
# имя сайта в зоне страны (`hr.ex.ru`) иначе приняли бы за такой уровень.
_ZONE_SECOND_LEVELS = frozenset({"co", "com", "net", "org", "ac", "gov", "edu"})


def site_label(host: str) -> str:
    """Имя сайта в хосте — без доменной зоны и поддоменов: `jobs.example.com` → `example`."""
    labels = host.split(".")
    if len(labels) >= 3 and len(labels[-1]) == 2 and labels[-2] in _ZONE_SECOND_LEVELS:
        return labels[-3]
    return labels[-2] if len(labels) >= 2 else labels[0]


def host_owns(host: str, link_host: str) -> bool:
    """Ссылка принадлежит сайту, если её хост равен его хосту или кончается на точку и его хост.

    Хвост берётся с точкой: `spb.hh.ru` — та же площадка, а `nothh.ru` — нет.
    """
    return link_host == host or link_host.endswith("." + host)


def owning_hosts(host: str) -> list[str]:
    """Хосты, которым принадлежит этот (`host_owns`): он сам и каждый, у кого он
    поддомен, — без голой доменной зоны: `spb.hh.ru` → `spb.hh.ru`, `hh.ru`.

    Отметка отсева на сайте ловится точным совпадением с любым из них — и
    поддомен сайта отсеивается так же, как ссылка на него.
    """
    labels = host.split(".")
    return [".".join(labels[at:]) for at in range(max(len(labels) - 1, 1))]


def owning_host(url: str, hosts: set[str]) -> str | None:
    """Хост из набора, которому принадлежит ссылка (`host_owns`); пусто — ничей.

    Набор перебирается по порядку, чтобы при двух подходящих — сайте и его
    поддомене в одном наборе — ответ не менялся от запуска к запуску.
    """
    link_host = normalize_host(url)
    if not link_host:
        return None
    return next((host for host in sorted(hosts) if host_owns(host, link_host)), None)


def page_owner(url: str, sites: list):
    """Сайт из списка, которому принадлежит страница (`owning_host`); пусто — ничей.

    Сайт — что угодно с полем `host`: агрегатор окна, строка обхода. Сайт без
    хоста — «Поиск по сети» — не владеет ничем.
    """
    host = owning_host(url, {site.host for site in sites if site.host})
    return next((site for site in sites if host and site.host == host), None)


LinkKind = Literal["article", "post", "channel", "telegram", "page"]
"""Куда ведёт ссылка, вставленная человеком."""


def article_address(url: str) -> str:
    """Адрес статьи так, как его узнаёт склейка статей: схема и хост строчными.

    Человек вставляет его как попало — без схемы, заглавными, — а склейка ищет
    статьи в тексте по одному написанию.
    """
    return f"https://{normalize_host(url)}/{address_parts(url.strip()).path}"


def typed_page(url: str | None) -> str | None:
    """Собственный адрес вакансии, набранной в «Полях»; пусто — его нет.

    Ссылка на пост Telegram у набранной — упоминание, а не её адрес: в посте
    бывает несколько вакансий, и вторая из них, сочтённая повтором первой,
    пропала бы вместе с набранным.
    """
    return url if url and post_address(url) is None else None


def row_address(source_url: str | None, msg_id: int | None) -> str | None:
    """Собственный адрес заведённой строки; пусто — его нет.

    Строка из поста — та, у которой есть номер сообщения: её ссылка на пост и
    есть её адрес. У строки без номера ссылка на пост — набранная в «Полях»
    (`typed_page`).
    """
    return source_url if msg_id is not None else typed_page(source_url)


def on_telegram(url: str) -> bool:
    """Ведёт ли адрес в Telegram или на его статьи — туда, что читает приём постов."""
    return owning_host(url, set(TELEGRAM_HOSTS)) is not None


def link_kind(url: str) -> LinkKind:
    """Род ссылки — одно правило по самому адресу: статья Telegraph, пост
    Telegram, иная ссылка Telegram на канал или приглашение, прочий Telegram —
    мгновенный просмотр, корень статей, — или любая другая страница.

    Прочий Telegram отдельным родом, а не страницей: агенту туда хода нет.
    """
    parts = address_parts(url.strip())
    if owning_host(url, set(TELEGRAPH_HOSTS)):
        # Распознаёт статью то же правило, что склейка в тексте поста: с начала
        # адреса, без хвостовой точки конца предложения.
        return "article" if ARTICLE_URL_RE.match(article_address(url)) else "telegram"
    if post_address(url) is not None:
        return "post"
    if owning_host(url, set(TELEGRAM_LINK_HOSTS)):
        return "telegram" if parts.path.split("/", 1)[0] in ("", "iv") else "channel"
    return "page"


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


class VacancyPage(NamedTuple):
    """Вид страницы вакансии на площадке: номер вакансии лежит в пути или в
    параметре адреса."""

    platform: str
    host: str
    path: re.Pattern
    query: str | None = None


_UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"

VACANCY_PAGES = (
    VacancyPage("hh", "hh.ru", re.compile(r"vacancy/(\d+)")),
    VacancyPage("habr", "habr.com", re.compile(r"vacancies/(\d+)")),
    VacancyPage("geekjob", "geekjob.ru", re.compile(r"vacancy/([0-9a-f]+)", re.I)),
    VacancyPage("getmatch", "getmatch.ru", re.compile(r"vacancies/(\d+)-.*")),
    VacancyPage("linkedin", "linkedin.com", re.compile(r"jobs/view/(\d+)"), "currentJobId"),
    VacancyPage("greenhouse-eu", "eu.greenhouse.io", re.compile(r"[^/]+/jobs/(\d+)"), "gh_jid"),
    VacancyPage("greenhouse", "greenhouse.io", re.compile(r"[^/]+/jobs/(\d+)"), "gh_jid"),
    VacancyPage("lever", "lever.co", re.compile(rf"[^/]+/({_UUID})(?:/.*)?", re.I)),
    VacancyPage("ashby", "ashbyhq.com", re.compile(rf"[^/]+/({_UUID})(?:/.*)?", re.I)),
)
"""Площадки, у которых одна страница вакансии — один номер.

Хост — тот, которому принадлежат страницы (`host_owns`): поддомены вроде
`spb.hh.ru` и `job-boards.greenhouse.io` — та же площадка. Строки сверяются по
порядку, первая подходящая и решает: у Greenhouse для Европы свой экземпляр, и
общий ли у него счёт номеров с основным, по адресу не сказать — поэтому он
стоит выше своей площадкой.
"""


def vacancy_address_key(url: str) -> str | None:
    """Ключ собственного адреса вакансии; пусто — однозначного ключа у адреса нет.

    Ключ — площадка и номер вакансии на ней, поэтому одна страница, записанная
    по-разному, даёт один ключ: метки прихода, поддомен, схема и косая в конце
    его не меняют. Адрес не по виду площадки — сайт компании, статья, страница
    без номера — ключа не получает: ложный повтор отказал бы человеку в новой
    вакансии, а пропущенный только заведёт вторую строку.

    `gh_jid` на сайте компании — номер Greenhouse, встроенного в чужую
    страницу; ключ ему пишется вместе с хостом сайта, потому что общий ли этот
    номер у разных сайтов, по адресу не сказать.

    Пост Telegram ключуется ником канала, как его записывает приём: ник может
    перейти к другому каналу, но тот же номер поста у нового владельца — случай,
    которого ждать не приходится.
    """
    post = post_address(url)
    if post is not None:
        return f"tg:{post.channel or post.private_id}:{post.msg_id}"
    parts = address_parts(url)
    if not parts.host:
        return None
    query = dict(parse_qsl(parts.query))
    for page in VACANCY_PAGES:
        if host_owns(page.host, parts.host):
            number = _page_number(page, parts.path, query)
            return f"{page.platform}:{number.lower()}" if number else None
    jid = query.get("gh_jid", "")
    return f"{parts.host}:gh:{jid}" if jid.isdigit() else None


def _page_number(page: VacancyPage, path: str, query: dict[str, str]) -> str | None:
    """Номер вакансии со страницы площадки: из пути, иначе из параметра."""
    match = page.path.fullmatch(path)
    if match is not None:
        return match[1]
    number = query.get(page.query, "") if page.query else ""
    return number if number.isdigit() else None


def is_arrival_mark(name: str) -> bool:
    """Параметр адреса, который говорит, откуда пришли, а не на что смотрят.

    Метки рекламы, кликов и сессии. Имя ждётся в нижнем регистре.
    """
    return (name.startswith("utm") or name.endswith(("clid", "clkid"))
            or "session" in name or name.endswith("sessid") or name in {"sid", "from"})


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
