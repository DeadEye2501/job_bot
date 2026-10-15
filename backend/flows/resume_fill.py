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
from backend.agent.sessions import end_reason, run_on_site
from backend.flows.aggregator_scan import scan
from backend.repository.aggregator_resumes import choose_resume, forbid_more_resumes, resumes_of
from backend.repository.profile_languages import read_user_language

logger = logging.getLogger(__name__)


async def fill(kit: AgentKit, source: Source, resume_id: int | None) -> str:
    """Перезаписать резюме `resume_id` или завести новое (пусто).

    Ответ — `ok`, `no_resume` (перезаписываемого резюме у сайта нет — агент не
    запускается), `no_editor` (у резюме нет адреса правки — агент не
    запускается: искать правку по сайту он приходил к созданию нового),
    `required_missing` (обязательному полю не хватило данных: перечня и
    отметки нет), `no_new_resume` (сайт не даёт завести ещё одно — флаг
    агрегатора «нельзя»), `error` (агент не довёл работу до конца) или ответ
    перечня, если он не удался. Заполненное резюме становится отмеченным: это
    единственная отметка, которую ставит не человек.
    """
    rows = await kit.read(lambda session: resumes_of(session, source.id))
    target = next((row for row in rows if row.id == resume_id), None)
    if resume_id is not None and target is None:
        return "no_resume"
    if target is not None and not target.editor_url:
        return "no_editor"
    resume_url = target.url if target else None
    await kit.browser.open_profile(source.id)
    job = FillJob(source, target.editor_url if target else None,
                  frozenset(row.editor_url for row in rows if row.editor_url and row is not target))
    files = (kit.pipeline.cv_file(), kit.pipeline.photo_file())
    language = await kit.read(read_user_language)
    end = await run_on_site(kit, job, FILL_PROMPT, fill_task(source.host, job.editor_url, language),
                            *fill_tools(kit, job), *browser_tools(kit, *files, job))
    result = job.outcome.result if isinstance(job.outcome, Finished) else None
    if result == "required_missing":
        return result
    if result == "no_new_resume":
        await kit.written(lambda session: forbid_more_resumes(session, source.id))
        return result
    _summary(job)
    if result != "done":
        logger.warning("заполнение резюме на %s: не доведено — %s", source.host, end_reason(job, end))
        return "error"
    scanned = await scan(kit, source)
    if scanned != "ok":
        return scanned
    await _mark_filled(kit, source.id, resume_url, {row.url for row in rows})
    return "ok"


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
