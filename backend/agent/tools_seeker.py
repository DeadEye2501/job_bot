"""Инструменты искателя: известна ли вакансия и передача найденного в конвейер."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from backend.agent.jobs import SeekJob
from backend.agent.kit import AgentKit
from backend.domain.hosts import source_key
from backend.flows import embeddings, intake, sameness
from backend.incoming import moment_or_none, str_list
from backend.models import ContactAddedBy, Vacancy
from backend.repository.aggregators import barred_host_of
from backend.repository.vacancies_life import source_seen
from backend.repository.vacancy_contacts import add_contact

WHAT = "найденная агентом вакансия"

BARRED = "сайт в чёрном списке человека"


def seeker_tools(kit: AgentKit, job: SeekJob, queue) -> list[Callable]:
    """Инструменты искателя, привязанные к своему источнику."""

    async def is_known(url: str) -> str:
        """Есть ли вакансия по этому адресу на этом источнике — заведённая или удалённая как мусор."""
        key, why = await _numbered(kit, job, url)
        if key is None:
            return why
        return "известна" if await _known(kit, job.source.id, key) else "новая"

    async def submit_vacancy(text: str, url: str, published: str, contacts: list[str]) -> str:
        """Передать вакансию в конвейер: дословный текст страницы, её адрес, дата публикации YYYY-MM-DD или пусто, контакты со страницы."""
        return await _submit(kit, job, queue, _Page(text, url, published, str_list(contacts)))

    return [is_known, submit_vacancy]


@dataclass(frozen=True)
class _Page:
    text: str
    url: str
    published: str
    contacts: list[str]


async def _submit(kit: AgentKit, job: SeekJob, queue, page: _Page) -> str:
    """Повтор по номеру — до предела и до эмбеддинга: он не стоит ни места в пределе, ни вызова модели.

    Сайт из отсева — пропуск, а не отказ: отказ обрывает обход, а вакансий с
    других сайтов человек ждёт по-прежнему.
    """
    key, why = await _numbered(kit, job, page.url)
    if key is None:
        return f"пропущена: {why}; иди дальше"
    if await _known(kit, job.source.id, key):
        return _left("повтор", job)
    if job.submitted >= job.limit:
        return "предел исчерпан; заверши работу: finish с result=\"done\""
    try:
        match = await sameness.known_or_new(kit.pipeline, page.text, WHAT)
    except embeddings.ProviderIsSilent:
        job.refused = True
        return "отказ: модель эмбеддингов не отвечает; заверши работу: finish с result=\"failed\""
    if match is None:
        return "пропущена: по тексту не вышло отпечатка; иди дальше"
    if match.kind == "unparsed" and match.vacancy_id not in job.found:
        # Своя находка этой сессии недоразобрана лишь потому, что ещё ждёт в очереди.
        queue.put(match.vacancy_id, page.text)
    if match.kind != "new":
        return _left("повтор", job)
    vacancy_id = await _store(kit, job, page, key, match.embedding)
    job.submitted += 1
    job.found.append(vacancy_id)
    queue.put(vacancy_id, page.text)
    kit.pipeline.emit_progress("aggregator", f"{job.source.name} — найдено", job.submitted, job.limit)
    return _left("принята", job)


def _left(answer: str, job: SeekJob) -> str:
    return f"{answer}; можно передать ещё {max(job.limit - job.submitted, 0)}"


async def _numbered(kit: AgentKit, job: SeekJob, url: str) -> tuple[str | None, str]:
    """Номер страницы на этом источнике — или пусто и причина, почему его нет.

    Причины две, и обе значат «не открывать и не передавать»: сайт из отсева и
    адрес не с этого источника. Отсев проверяется первым: его страница могла бы
    оказаться и на этом источнике, а человеку она не нужна всё равно.
    """
    if await _barred(kit, url):
        return None, f"{BARRED} — не открывай"
    key = source_key(url, job.source.host)
    return key, "" if key is not None else "адрес не с этого источника"


async def _barred(kit: AgentKit, url: str) -> bool:
    """Адрес ведёт на сайт из отсева — его вакансии человеку не нужны."""
    async with kit.pipeline.session_factory() as session:
        return await barred_host_of(session, [url]) is not None


async def _known(kit: AgentKit, aggregator_id: int, key: str) -> bool:
    """Номер уже видели: вакансия с ним заведена или удалена как мусор."""
    async with kit.pipeline.session_factory() as session:
        return await source_seen(session, aggregator_id, key)


async def _store(kit: AgentKit, job: SeekJob, page: _Page, key: str, embedding: list[float]) -> int:
    """Завести вакансию, затем её контакты своей транзакцией.

    Адрес самой страницы ложится и в контакты, первым: человек ищет ссылку на
    вакансию в её контактах, рядом с остальными, а не только в шапке карточки.

    Контакты пишутся до очереди разбора: разбор трогает только свои строки.
    Одной транзакцией с вакансией их не сделать без пятого довода у
    `intake.save_new_vacancy`; оборвись запись между ними, вакансия останется
    без контактов со страницы, но ссылка на саму страницу — в `source_url`.
    """
    row = Vacancy(
        raw_text=page.text, embedding=embedding, source_aggregator_id=job.source.id,
        source_key=key, source_url=page.url, posted_at=_posted(page.published),
    )
    # «Поиск по сети» — способ поиска, а не место: окно подписывает такую
    # находку своими словами, и знать об этом ему неоткуда, кроме события.
    found = {"source": job.source.name, "url": page.url, "web_search": job.source.host is None}
    vacancy_id = await intake.save_new_vacancy(kit.pipeline, row, "found", found)
    async def contacts(session) -> None:
        for value in (page.url, *page.contacts):
            await add_contact(session, vacancy_id, value, ContactAddedBy.AGENT)

    await kit.written(contacts)
    return vacancy_id


def _posted(published: str) -> datetime | None:
    """Дата публикации со страницы; без пояса — UTC, неразборчивая — пусто."""
    posted = moment_or_none(published)
    if posted is not None and posted.tzinfo is None:
        return posted.replace(tzinfo=timezone.utc)
    return posted
