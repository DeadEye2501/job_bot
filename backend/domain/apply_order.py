"""Какими способами откликнуться и в каком порядке: кнопка агрегатора, форма, почта.

Telegram в перечне нет: отклик в Telegram делает своя фаза раньше.
"""

from dataclasses import dataclass

from backend.domain.contact_keys import is_address, is_link
from backend.domain.hosts import host_owns, normalize_host
from backend.models import ApplicationVia

_AGGREGATOR = ApplicationVia.AGGREGATOR.value
_FORM = ApplicationVia.FORM.value
_EMAIL = ApplicationVia.EMAIL.value


@dataclass(frozen=True)
class Way:
    method: str
    target: str
    aggregator_id: int | None


@dataclass(frozen=True)
class KnownSite:
    """Агрегатор человека; пустой хост — «Поиск по сети». Без входа его кнопка
    не работает, но формой работодателя его страница всё равно не бывает."""

    id: int
    host: str | None
    logged_in: bool = True


@dataclass(frozen=True)
class ApplyFacts:
    """Что известно о вакансии для выбора способов.

    `source_site` — агрегатор, с которого она пришла (у вакансии из канала —
    пусто); `sites` — все агрегаторы человека; `closed` — закрытые до конца обхода.
    """

    source_url: str | None
    source_site: KnownSite | None
    contacts: list[str]
    sites: list[KnownSite]
    mail_ready: bool
    closed: set[int]


def apply_ways(facts: ApplyFacts) -> list[Way]:
    """Способы по порядку: кнопка агрегатора, форма, затем каждый адрес почты."""
    ways = [way for way in (_button(facts), _form(facts)) if way is not None]
    if facts.mail_ready:
        ways += [Way(_EMAIL, c.strip(), None) for c in facts.contacts if is_address(c)]
    return ways


def _button(facts: ApplyFacts) -> Way | None:
    """Ссылка на вакансию на сайте залогиненного и не закрытого агрегатора."""
    for link in _links(facts):
        site = _owner(link, facts.sites)
        if site is not None and site.logged_in and site.id not in facts.closed:
            return Way(_AGGREGATOR, link, site.id)
    return None


def _form(facts: ApplyFacts) -> Way | None:
    """Своя страница у находки поиска по сети, иначе любая ссылка не на агрегатор человека."""
    source = facts.source_site
    if source is not None and source.host is None and facts.source_url:
        return Way(_FORM, facts.source_url, None)
    contact_links = [c.strip() for c in facts.contacts if is_link(c)]
    return next((Way(_FORM, link, None) for link in contact_links
                 if _owner(link, facts.sites) is None), None)


def _links(facts: ApplyFacts) -> list[str]:
    from_source = [facts.source_url] if facts.source_site and facts.source_site.host and facts.source_url else []
    return from_source + [c.strip() for c in facts.contacts if is_link(c)]


def _owner(link: str, sites: list[KnownSite]) -> KnownSite | None:
    host = normalize_host(link)
    return next((s for s in sites if s.host and host_owns(s.host, host)), None)
