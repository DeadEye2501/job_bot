"""Заполнение резюме на сайте агрегатора по анкете.

Следом за агентом — перечень резюме и отметка заполненного.

От перечня (`aggregator_scan`) отличается тем, что меняет сайт: браузер
открыт с правом сохранять, ввод — строгий, только принятое в раскладке.
"""

import logging

from backend.agent.jobs import FillJob, Finished, Source
from backend.agent.kit import AgentKit
from backend.agent.prompts.fill import FILL_PROMPT, fill_task
from backend.agent.tools_browser import browser_tools
from backend.agent.tools_fill import fill_tools
from backend.agent.sessions import run_on_site
from backend.flows.aggregator_scan import scan
from backend.repository.aggregator_resumes import choose_resume, resumes_of

logger = logging.getLogger(__name__)


async def fill(kit: AgentKit, source: Source, resume_id: int | None) -> str:
    """Перезаписать резюме `resume_id` или завести новое (пусто).

    Ответ — `ok`, `required_missing` (обязательному полю не хватило данных:
    перечня и отметки нет), `error` (агент не довёл работу до конца) или
    ответ перечня, если он не удался. Заполненное резюме становится
    отмеченным: это единственная отметка, которую ставит не человек.
    """
    before = await _links(kit, source.id)
    if resume_id is not None and resume_id not in before:
        return "missing"
    resume_url = before.get(resume_id)
    await kit.browser.open_profile(source.id)
    job = FillJob(source, resume_url)
    files = (kit.pipeline.cv_file(), kit.pipeline.photo_file())
    end = await run_on_site(kit, job, FILL_PROMPT, fill_task(source.host, resume_url),
                            *fill_tools(kit, job), *browser_tools(kit, *files, job))
    result = job.outcome.result if isinstance(job.outcome, Finished) else None
    if result == "required_missing":
        return result
    _summary(job)
    if result is None:
        logger.warning("заполнение резюме на %s: без итога — %s", source.host, end.detail or "агент молчал")
        return "error"
    scanned = await scan(kit, source)
    if scanned != "ok":
        return scanned
    await _mark_filled(kit, source.id, resume_url, set(before.values()))
    return "ok"


async def _links(kit: AgentKit, aggregator_id: int) -> dict[int, str]:
    """Ссылки резюме сайта по номеру — до заполнения: по ним узнаётся новое."""
    async with kit.pipeline.session_factory() as session:
        return {row.id: row.url for row in await resumes_of(session, aggregator_id)}


async def _mark_filled(kit: AgentKit, aggregator_id: int, resume_url: str | None, before: set[str]) -> None:
    """Отметить заполненное: резюме по его прежней ссылке, иначе — единственная
    ссылка, которой до заполнения не было. Перезапись может сменить ссылку, а
    при нескольких новых какая из них заполнена, не знает никто — отметку
    тогда ставит человек."""

    async def mark(session) -> None:
        rows = await resumes_of(session, aggregator_id)
        same = [row for row in rows if row.url == resume_url]
        new = [row for row in rows if row.url not in before]
        filled = same or (new if len(new) == 1 else [])
        if not filled:
            logger.warning("заполнение резюме: какое резюме заполнено, по перечню сайта не понять")
            return
        await choose_resume(session, aggregator_id, filled[0].id)

    await kit.written(mark)


def _summary(job: FillJob) -> None:
    """Сводка в журнал: страниц, данных запасным путём и пропущенных необязательных полей."""
    pages = {url for url, _ in job.accepted} | set(job.skipped)
    fallbacks = sum(1 for item in job.accepted.values() if item.get("fallback_reason"))
    skipped = sorted({label for labels in job.skipped.values() for label in labels})
    logger.info("заполнение резюме на %s: страниц %d, запасным путём %d, пропущено необязательных: %s",
                job.source.host, len(pages), fallbacks, ", ".join(skipped) or "нет")
