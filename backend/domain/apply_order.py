"""Какими способами откликнуться и в каком порядке."""

from dataclasses import dataclass

from backend.domain.contact_keys import contact_key, is_address, is_link
from backend.domain.hosts import on_telegram, page_owner
from backend.domain.spellings import dedupe_first_wins
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
    """Агрегатор человека; пустой хост — «Поиск по сети». Без входа или без
    выбранного резюме его кнопка не работает, но формой работодателя его
    страница всё равно не бывает."""

    id: int
    host: str | None
    logged_in: bool = True
    resume_chosen: bool = True


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
    """Способы по порядку: Telegram, кнопки агрегаторов, формы, почта.

    Каждая ссылка — свой способ, как каждый адрес почты: из двух страниц
    выбирает человек в окне, а откликатель при неудаче первой идёт ко второй.
    """
    ways = [_telegram(vacancy, world)]
    if world.agent_ready:
        ways += _buttons(vacancy, world) + _forms(vacancy, world)
    if world.mail_ready:
        ways += [Way(VIA_EMAIL, c.strip(), None) for c in vacancy.contacts if is_address(c)]
    return [way for way in ways if way is not None]


def _telegram(vacancy: VacancyFacts, world: World) -> Way | None:
    if vacancy.hr_handle is None or not world.telegram_open:
        return None
    return Way(VIA_TELEGRAM, vacancy.hr_handle, None)


def _buttons(vacancy: VacancyFacts, world: World) -> list[Way]:
    """Ссылки на вакансию на сайте агрегатора со входом, выбранным резюме и не закрытого.

    Без выбранного резюме откликаться нечем: угаданное резюме могло бы оказаться
    резюме другой профессии.
    """
    ways = []
    for link in _links(vacancy):
        site = page_owner(link, world.sites)
        if (site is not None and site.logged_in and site.resume_chosen
                and site.id not in world.closed_sites):
            ways.append(Way(VIA_AGGREGATOR, link, site.id))
    return ways


def _forms(vacancy: VacancyFacts, world: World) -> list[Way]:
    """Своя страница у находки поиска по сети и все ссылки не на агрегатор человека.

    Страница агрегатора человека формой не бывает и у находки сети: веб-поиск
    обходит их по наставлению, а не по запрету, и принести может. Страница-источник
    вакансии с площадки формой не бывает тоже — это страница площадки.
    """
    web_find = vacancy.source_site is not None and vacancy.source_site.host is None
    return [Way(VIA_FORM, link, None) for link in _links(vacancy)
            if (web_find or link != vacancy.source_url) and page_owner(link, world.sites) is None]


def _links(vacancy: VacancyFacts) -> list[str]:
    """Страница-источник у вакансии с сайта, затем ссылки из контактов, без повторов.

    Источник канала — пост в Telegram, а не страница вакансии, поэтому берётся
    только у вакансии с площадки или из сети. Повтор — та же страница,
    записанная ещё и контактом: два способа на один адрес были бы одним.
    """
    from_source = [vacancy.source_url] if vacancy.source_site and vacancy.source_url else []
    return dedupe_first_wins(from_source + _contact_links(vacancy), key=contact_key)


def _contact_links(vacancy: VacancyFacts) -> list[str]:
    """Ссылки из контактов — кроме Telegram: та — контакт Telegram, из неё
    заводится HR, и пишут ему письмом в Telegram, а не формой в браузере."""
    return [c.strip() for c in vacancy.contacts if is_link(c) and not on_telegram(c)]
