"""Инструменты перечня резюме: отчёт о резюме человека на сайте агрегатора."""

from collections.abc import Callable

from backend.agent.jobs import ScanJob
from backend.agent.kit import AgentKit
from backend.payloads import SeenResume
from backend.repository.aggregator_resumes import sync_resumes


def scan_tools(kit: AgentKit, job: ScanJob) -> list[Callable]:
    """Инструменты перечня, привязанные к своему сайту.

    Резюме приходит готовым `SeenResume`: схему по подписи строит FastMCP
    (pydantic), он же собирает из ответа агента сами записи.
    """

    async def report_resumes(resumes: list[SeenResume], can_add: bool) -> str:
        """Резюме человека на сайте в порядке сайта (название, ссылка на страницу резюме) и можно ли завести ещё одно."""
        await kit.written(lambda session: sync_resumes(session, job.source.id, resumes, can_add))
        job.reported = True
        return "Список резюме записан."

    return [report_resumes]
