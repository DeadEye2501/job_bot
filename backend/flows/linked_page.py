"""Страница вакансии по ссылке человека: агент открывает её и заводит вакансию.

Отличие от `aggregator_round`: там искатель ищет по выдаче и курсору обхода,
здесь — одна страница по заданному адресу, которую человек уже выбрал. Сессия,
инструменты, сроки, профиль браузера и цикл находки у них общие.
"""

from backend.agent.jobs import Finished, SeekJob, Source
from backend.agent.kit import AgentKit, SessionPlan
from backend.agent.prompts.frame import system_prompt
from backend.agent.prompts.seeker import PAGE_PROMPT, page_task
from backend.domain.hosts import page_owner
from backend.flows.aggregator_round import run_seeker_on
from backend.flows.hand_outcome import show_parsing, tell
from backend.flows.handover import Intake
from backend.repository.aggregators import list_aggregators, web_search_row


async def ingest_page(kit: AgentKit, url: str, intake: Intake) -> None:
    """Завести вакансию со страницы; итог окну — вестью.

    Источник — заведённый агрегатор, если страница его, даже с выключенным
    обходом: у него свой профиль браузера и вход; иначе «Поиск по сети».

    Агент ничего не передал и кончил сессию сам — на странице нет вакансии.
    Сорвался — капча, вход, срок — это беда, а не пустая страница: окну её
    скажет бот по концу работы, где итога не прозвучало (`bot/pasted`).
    """
    show_parsing(kit.pipeline)
    job = SeekJob(await _source(kit, url), 1, page=url, intake=intake)

    async def plan(tools: list) -> SessionPlan:
        return SessionPlan(system_prompt(PAGE_PROMPT, tools), page_task(url), tools, web_search=False)

    await run_seeker_on(kit, job, plan)
    if job.submitted == 0 and isinstance(job.outcome, Finished) and job.outcome.result == "done":
        tell(kit.pipeline, "no_vacancy")


async def _source(kit: AgentKit, url: str) -> Source:
    """Агрегатор, которому принадлежит страница, иначе «Поиск по сети»."""
    async with kit.pipeline.session_factory() as session:
        owner = page_owner(url, await list_aggregators(session)) or await web_search_row(session)
    return Source.of(owner)
