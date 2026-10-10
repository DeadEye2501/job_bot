"""Какими способами откликнуться и в каком порядке."""

from dataclasses import dataclass

from backend.domain.contact_keys import is_address, is_link
from backend.domain.hosts import owning_host
from backend.models import ApplicationVia

VIA_TELEGRAM = ApplicationVia.TELEGRAM.value
VIA_AGGREGATOR = ApplicationVia.AGGREGATOR.value
VIA_FORM = ApplicationVia.FORM.value
VIA_EMAIL = ApplicationVia.EMAIL.value
"""Способы отклика строкой — так их несут `Way` и задание агента."""


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
class VacancyFacts:
    """Что о вакансии нужно выбору способа. `hr_handle` — адрес HR в Telegram
    словом окна (`@ник` или номер); `source_site` — площадка, с которой она пришла."""

    hr_handle: str | None
    source_url: str | None
    source_site: KnownSite | None
    contacts: list[str]


@dataclass
class World:
    """Что сейчас доступно. Живёт прогон откликателя: исполнитель доучивает его."""

    telegram_open: bool
    mail_ready: bool
    agent_ready: bool
    sites: list[KnownSite]
    closed_sites: set[int]


def apply_ways(vacancy: VacancyFacts, world: World) -> list[Way]:
    """Способы по порядку: Telegram, кнопка агрегатора, форма, каждый адрес почты."""
    ways = [_telegram(vacancy, world)]
    if world.agent_ready:
        ways += [_button(vacancy, world), _form(vacancy, world)]
    if world.mail_ready:
        ways += [Way(VIA_EMAIL, c.strip(), None) for c in vacancy.contacts if is_address(c)]
    return [way for way in ways if way is not None]


def _telegram(vacancy: VacancyFacts, world: World) -> Way | None:
    if vacancy.hr_handle is None or not world.telegram_open:
        return None
    return Way(VIA_TELEGRAM, vacancy.hr_handle, None)


def _button(vacancy: VacancyFacts, world: World) -> Way | None:
    """Ссылка на вакансию на сайте залогиненного и не закрытого агрегатора."""
    for link in _links(vacancy):
        site = _owner(link, world.sites)
        if site is not None and site.logged_in and site.id not in world.closed_sites:
            return Way(VIA_AGGREGATOR, link, site.id)
    return None


def _form(vacancy: VacancyFacts, world: World) -> Way | None:
    """Своя страница у находки поиска по сети, иначе любая ссылка не на агрегатор человека.

    Страница агрегатора человека формой не бывает и у находки сети: веб-поиск
    обходит их по наставлению, а не по запрету, и принести может.
    """
    source = vacancy.source_site
    web_find = source is not None and source.host is None and vacancy.source_url
    candidates = [vacancy.source_url] if web_find else []
    return next((Way(VIA_FORM, link, None) for link in candidates + _contact_links(vacancy)
                 if _owner(link, world.sites) is None), None)


def _links(vacancy: VacancyFacts) -> list[str]:
    from_source = [vacancy.source_url] if vacancy.source_site and vacancy.source_url else []
    return from_source + _contact_links(vacancy)


def _contact_links(vacancy: VacancyFacts) -> list[str]:
    return [c.strip() for c in vacancy.contacts if is_link(c)]


def _owner(link: str, sites: list[KnownSite]) -> KnownSite | None:
    host = owning_host(link, {s.host for s in sites if s.host})
    return next((s for s in sites if host and s.host == host), None)
