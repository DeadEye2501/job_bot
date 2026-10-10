"""Инструменты откликателя: своя вакансия и запись отклика на сайте."""

from collections.abc import Callable
from dataclasses import dataclass

from backend.agent.jobs import Applied, ApplyJob
from backend.agent.kit import AgentKit
from backend.domain.apply_order import VIA_AGGREGATOR, VIA_FORM
from backend.models import ApplicationVia
from backend.repository.applications import ApplicationEntry, append_screening
from backend.repository.applications import record_application as store
from backend.repository.vacancy_brief import describe_vacancy

# Кнопка агрегатора бывает переходом на форму работодателя: такой отклик пишется формой.
_ALLOWED = {VIA_AGGREGATOR: {VIA_AGGREGATOR, VIA_FORM}, VIA_FORM: {VIA_FORM}}


def applier_tools(kit: AgentKit, job: ApplyJob) -> list[Callable]:
    """Инструменты откликателя, привязанные к своей вакансии и своему способу."""

    async def vacancy() -> str:
        """Своя вакансия: название, компания, источник, адрес страницы, контакты и текст."""
        async with kit.pipeline.session_factory() as session:
            return await describe_vacancy(session, job.vacancy_id) or "Вакансия удалена."

    async def record_application(
        via: str, target: str, letter: str = "", screening: list[dict] | None = None,
        already_applied: bool = False,
    ) -> str:
        """Записать отклик, который сайт подтвердил: aggregator или form, адрес страницы или формы, письмо, вопросы и ответы скрининга по порядку. Повтор с тем же адресом дописывает скрининг."""
        if via not in _ALLOWED[job.way.method]:
            return "Этим способом отклик не пишется."
        lines = _lines(screening or [])
        if isinstance(job.outcome, Applied):
            return await _append(kit, job.outcome.application_id, lines)
        letter_text = None if already_applied else (letter or None)
        return await _record(kit, job, _entry(job, _Report(via, target, letter_text, lines)))

    return [vacancy, record_application]


@dataclass(frozen=True)
class _Report:
    """Что о состоявшемся отклике сообщил агент."""

    via: str
    target: str
    letter: str | None
    screening: list[tuple[bool, str]]


def _entry(job: ApplyJob, report: _Report) -> ApplicationEntry:
    return ApplicationEntry(
        vacancy_id=job.vacancy_id, aggregator_id=job.way.aggregator_id,
        via=ApplicationVia(report.via), target=report.target, letter=report.letter,
        letter_by=job.letter_writer if report.letter else None,
        screening=report.screening, simulated=job.simulated,
    )


def _lines(screening: list[dict]) -> list[tuple[bool, str]]:
    return [(bool(x.get("from_us")), str(x.get("text", ""))) for x in screening if isinstance(x, dict)]


async def _record(kit: AgentKit, job: ApplyJob, entry: ApplicationEntry) -> str:
    job.outcome = Applied(await record_and_announce(kit, entry))
    return "Отклик записан."


async def record_and_announce(kit: AgentKit, entry: ApplicationEntry) -> int:
    """Записать отклик своей сделкой и дать окну весть; ответ — номер отклика."""
    application_id = await kit.written(lambda session: store(session, entry))
    kit.pipeline.fire_vacancies_changed()
    return application_id


async def _append(kit: AgentKit, application_id: int, lines: list[tuple[bool, str]]) -> str:
    """Скрининг к отклику, уже записанному в этой сессии: вопросы со страницы
    подтверждения ложатся туда же, даже если её адрес другой."""
    await kit.written(lambda session: append_screening(session, application_id, lines))
    return "Скрининг дописан к записанному отклику."
