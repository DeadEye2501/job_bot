"""Инструменты искателя: известна ли вакансия и передача найденного в конвейер."""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from backend.agent.jobs import SeekJob
from backend.agent.kit import AgentKit
from backend.agent.stops import RUN_STOPPERS
from backend.domain.hosts import host_owns, normalize_host, on_telegram, source_key
from backend.flows import embeddings, hand_repeat, handover, intake, pasted, sameness
from backend.flows.hand_outcome import show_parsing
from backend.incoming import moment_or_none, str_list
from backend.models import ContactAddedBy, Vacancy
from backend.repository.aggregators import barred_host_of
from backend.repository.vacancies_life import source_row, source_seen
from backend.repository.vacancy_contacts import add_contact

logger = logging.getLogger(__name__)

WHAT = "найденная агентом вакансия"

BARRED = "сайт в чёрном списке человека"

TELEGRAM_OWN = "у Telegram свой обход"

STOPPED = 'Работа остановлена: заверши сессию — finish с result="failed"'

LIMIT_REACHED = 'предел исчерпан; заверши работу: finish с result="done"'

# Цикл находки уводит вкладку — у отклика свой профиль и свои страницы, — и
# «назад» по её истории искатель пришёл бы не к выдаче.
BACK = "вкладка могла уйти: вернись к выдаче — browser_open её адреса — и продолжай со следующей вакансии"


NOT_THIS_PAGE = (
    'не та страница: передавай вакансию только со страницы из задания; '
    'нет её там — заверши работу: finish с result="done"'
)


def seeker_tools(kit: AgentKit, job: SeekJob) -> list[Callable]:
    """Инструменты искателя, привязанные к своему источнику.

    Искателю страницы человека (`job.page`) спрашивать, известна ли вакансия,
    незачем: он ничего не ищет, а заводит одну, которую человек уже выбрал.
    """

    async def is_known(url: str) -> str:
        """Есть ли вакансия по этому адресу на этом источнике — заведённая или удалённая как мусор."""
        if job.stopper is not None:
            return STOPPED
        key, why = await _numbered(kit, job, url)
        if key is None:
            return why
        return "известна" if await _known(kit, job.source.id, key) else "новая"

    async def submit_vacancy(text: str, url: str, published: str, contacts: list[str]) -> str:
        """Передать вакансию в конвейер: дословный текст страницы, её адрес, дата публикации YYYY-MM-DD или пусто, контакты со страницы."""
        page = _Page(text, url, published, str_list(contacts))
        return await (_submit(kit, job, page) if job.page is None else _submit_page(kit, job, page))

    return [submit_vacancy] if job.page is not None else [is_known, submit_vacancy]


@dataclass(frozen=True)
class _Page:
    text: str
    url: str
    published: str
    contacts: list[str]


async def _submit(kit: AgentKit, job: SeekJob, page: _Page) -> str:
    """Повтор по номеру — до предела и до эмбеддинга: он не стоит ни места в пределе, ни вызова модели.

    Сайт из отсева — пропуск, а не отказ: отказ обрывает обход, а вакансий с
    других сайтов человек ждёт по-прежнему.
    """
    if job.stopper is not None:
        return STOPPED
    key, why = await _numbered(kit, job, page.url)
    if key is None:
        return f"пропущена: {why}; иди дальше"
    if await _known(kit, job.source.id, key):
        return _left("повтор", job)
    if job.submitted >= job.limit:
        return LIMIT_REACHED
    return await _by_fingerprint(kit, job, page, key)


async def _by_fingerprint(kit: AgentKit, job: SeekJob, page: _Page, key: str) -> str:
    """Судьба находки по отпечатку: разобранная — повтор, брошенная — дочитать,
    новая — завести.

    Новая и брошенная недоразобранной проходят весь цикл до ответа агенту
    (`_through`): следующую он ищет, когда по этой всё кончено.
    """
    try:
        match = await sameness.known_or_new(kit.pipeline, page.text, WHAT)
    except embeddings.ProviderIsSilent:
        job.refused = True
        return "отказ: модель эмбеддингов не отвечает; заверши работу: finish с result=\"failed\""
    if match is None:
        return "пропущена: по тексту не вышло отпечатка; иди дальше"
    if match.kind == "parsed":
        return _left("повтор", job)
    if match.kind == "unparsed":
        return await _through(kit, job, "повтор", handover.finish_orphan(
            kit.pipeline, match.vacancy_id, page.text, job.intake))
    vacancy_id = await _store(kit, job, page, key, match.embedding)
    job.submitted += 1
    return await _through(kit, job, "принята", handover.judge_and_hand_over(
        kit.pipeline, vacancy_id, page.text, job.intake))


async def _submit_page(kit: AgentKit, job: SeekJob, page: _Page) -> str:
    """Вакансия со страницы человека: заведённая вручную, своей строкой.

    Чёрный список и сходство с заведёнными — подсказки автоматике, и здесь их
    нет: человек сам выбрал страницу. Однозначный повтор — тот же номер на том
    же источнике (`source_key`), только у живой строки: снесённую мусором
    человек вправе завести снова. Страница с другого сайта — переадресация, а
    не его вакансия.
    """
    if job.stopper is not None:
        return STOPPED
    if job.submitted >= job.limit:
        return LIMIT_REACHED
    # Переадресацию на чужой сайт у площадки отсекает сам `source_key`; у
    # «Поиска по сети» хозяина нет, и им становится сайт вставленной страницы.
    same_site = job.source.host is not None or host_owns(normalize_host(job.page), normalize_host(page.url))
    key = source_key(page.url, job.source.host) if same_site else None
    if key is None:
        return NOT_THIS_PAGE
    # Одна страница — одна попытка (предел задачи страницы — одна): итог её
    # окно слышит один раз, чем бы она ни кончилась.
    job.submitted += 1
    existing = await kit.read(lambda session: source_row(session, job.source.id, key))
    if existing is not None and await hand_repeat.known_and_told(kit.pipeline, [existing]):
        return f"повтор; {LIMIT_REACHED}"

    async def save(embedding: list[float]) -> int:
        return await _store(kit, job, page, key, embedding)

    return await _through(kit, job, "принята", pasted.file_by_hand(kit.pipeline, page.text, job.intake, save))


async def _through(kit: AgentKit, job: SeekJob, answer: str, cycle: Awaitable) -> str:
    """Провести находку по циклу — разбор, оценка, передача, отклик — и вернуть
    искателю его браузер и полосу.

    Беда, снимающая работу (`RUN_STOPPERS`), снимает и поиск: агент слышит
    «заверши», а сама беда ждёт конца сессии в `job.stopper`. Прочая беда — одной
    находки: запись в журнал, и поиск идёт дальше.
    """
    job.nested = True
    try:
        await cycle
        said = _left(answer, job)
    except RUN_STOPPERS as stopper:
        job.stopper = stopper
        return STOPPED
    except Exception:
        logger.exception("цикл находки искателя на %s: сбой", job.source.name)
        said = "не вышло: на этой вакансии сбой приложения"
    finally:
        job.nested = False
    await kit.browser.open_profile(job.source.id)
    _show_bar(kit, job)
    return f"{said}; {LIMIT_REACHED if job.submitted >= job.limit else BACK}"


def _show_bar(kit: AgentKit, job: SeekJob) -> None:
    """Нижняя полоса снова за искателем: у обхода — ход обхода, а там, где
    итога ждёт окно, — разбор объявления, как у вставленного текста."""
    if job.intake.by_hand:
        show_parsing(kit.pipeline)
    else:
        kit.pipeline.emit_progress("aggregator", job.source.sweep, job.submitted, job.limit)


def _left(answer: str, job: SeekJob) -> str:
    return f"{answer}; можно передать ещё {max(job.limit - job.submitted, 0)}"


async def _numbered(kit: AgentKit, job: SeekJob, url: str) -> tuple[str | None, str]:
    """Номер страницы на этом источнике — или пусто и причина, почему его нет.

    Причины три, и все значат «не открывать и не передавать»: страница
    Telegram, сайт из отсева и адрес не с этого источника. Отсев проверяется
    раньше источника: его страница могла бы оказаться и на этом источнике, а
    человеку она не нужна всё равно. Telegram — не отсев: его каналы и статьи
    читает приём постов, и человек их не запрещал. Поэтому он и проверяется
    первым — запрет действует всегда, есть ли такой хост в отсеве или нет.
    """
    if on_telegram(url):
        return None, f"{TELEGRAM_OWN} — не открывай"
    if await _barred(kit, url):
        return None, f"{BARRED} — не открывай"
    key = source_key(url, job.source.host)
    return key, "" if key is not None else "адрес не с этого источника"


async def _barred(kit: AgentKit, url: str) -> bool:
    """Адрес ведёт на сайт из отсева — его вакансии человеку не нужны."""
    return await kit.read(lambda session: barred_host_of(session, [url])) is not None


async def _known(kit: AgentKit, aggregator_id: int, key: str) -> bool:
    """Номер уже видели: вакансия с ним заведена или удалена как мусор."""
    return await kit.read(lambda session: source_seen(session, aggregator_id, key))


async def _store(kit: AgentKit, job: SeekJob, page: _Page, key: str, embedding: list[float]) -> int:
    """Завести вакансию, затем её контакты своей транзакцией.

    Адрес самой страницы ложится и в контакты, первым: человек ищет ссылку на
    вакансию в её контактах, рядом с остальными, а не только в шапке карточки.

    Контакты пишутся до разбора: разбор трогает только свои строки.
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
    vacancy_id = await intake.save_new_vacancy(kit.pipeline, row, *job.intake.event("found", found))
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
