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

    Можно ли завести ещё одно резюме, решает агент по признакам на сайте, а
    не код по адресам: адрес создания нового на одних сайтах совпадает с
    правкой существующего, и по адресам их не различить. Какие признаки агент
    нашёл, пишется в журнал — по ним решение проверяется.
    """

    async def report_resumes(resumes: list[SeenResume], many_resumes: bool, signs_found: str) -> str:
        """Резюме человека на сайте в порядке сайта: название и ссылка на страницу резюме. many_resumes — даёт ли сайт держать несколько резюме; signs_found — какие признаки этого нашёл и где, словами."""
        logger.info("перечень резюме на %s: резюме %d, можно ещё одно — %s (%s)",
                    job.source.host, len(resumes), "да" if many_resumes else "нет", signs_found)
        await kit.written(lambda session: sync_resumes(session, job.source.id, resumes, many_resumes))
        job.reported = True
        return "Список резюме записан."

    return [report_resumes]
