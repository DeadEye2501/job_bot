"""Инструменты перечня резюме: отчёт о резюме человека на сайте агрегатора."""

import logging
from collections.abc import Callable

from backend.agent.jobs import ScanJob
from backend.agent.kit import AgentKit
from backend.payloads import SeenResume
from backend.repository.aggregator_resumes import sync_resumes

logger = logging.getLogger(__name__)


def scan_tools(kit: AgentKit, job: ScanJob) -> list[Callable]:
    """Инструменты перечня, привязанные к своему сайту.

    Резюме приходит готовым `SeenResume`: схему по подписи строит FastMCP
    (pydantic), он же собирает из ответа агента сами записи.

    Можно ли завести ещё одно резюме, решается по адресу, который приносит
    агент: адрес виден в журнале, и решение по нему можно проверить. Адрес,
    ведущий к уже перечисленному резюме, новым не считается — это правка того же.
    """

    async def report_resumes(resumes: list[SeenResume], new_resume_url: str | None) -> str:
        """Резюме человека на сайте в порядке сайта (название, ссылка на страницу резюме) и адрес, по которому сайт заводит новое отдельное резюме; нет такого — null."""
        can_add = bool(new_resume_url) and new_resume_url not in {r.url for r in resumes}
        logger.info("перечень резюме на %s: резюме %d, адрес нового резюме — %s",
                    job.source.host, len(resumes), new_resume_url)
        await kit.written(lambda session: sync_resumes(session, job.source.id, resumes, can_add))
        job.reported = True
        return "Список резюме записан."

    return [report_resumes]
