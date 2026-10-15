"""Инструменты откликателя: своя вакансия и запись отклика на сайте."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, TypedDict

from pydantic import StringConstraints

from backend.agent.confirm import is_checked
from backend.agent.jobs import FINAL_ANSWER, Applied, ApplyJob, Dropped
from backend.agent.kit import AgentKit
from backend.domain.apply_order import VIA_AGGREGATOR, VIA_FORM
from backend.models import ApplicationVia
from backend.repository.applications import ApplicationEntry, append_screening
from backend.repository.applications import record_application as store
from backend.repository.vacancy_brief import describe_vacancy

# Кнопка агрегатора бывает переходом на форму работодателя: такой отклик пишется формой.
_ALLOWED = {VIA_AGGREGATOR: {VIA_AGGREGATOR, VIA_FORM}, VIA_FORM: {VIA_FORM}}

_Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


# По этому типу MCP строит схему инструмента: пара без текста отклоняется
# агенту при вызове, и ниже по потоку проверять её уже нечего.
class ScreeningPair(TypedDict):
    """Вопрос работодателя и ответ человека на него."""

    question: _Text
    answer: _Text


@dataclass(frozen=True)
class _Report:
    """Что о состоявшемся отклике известно: от агента или из подтверждённого."""

    via: str
    target: str
    letter: str | None
    screening: list[tuple[bool, str]]


def applier_tools(kit: AgentKit, job: ApplyJob) -> list[Callable]:
    """Инструменты откликателя, привязанные к своей вакансии и своему способу."""

    async def vacancy() -> str:
        """Своя вакансия: название, компания, источник, адрес страницы, контакты и текст."""
        return await kit.read(lambda session: describe_vacancy(session, job.vacancy_id)) or "Вакансия удалена."

    # Под подтверждением письмо и ответы уже известны — их подтвердил человек, —
    # и агенту запись отдаётся без них: пересказ, который выбросили бы, не просят.
    return [vacancy, _confirmed_record(kit, job) if job.confirming else _reported_record(kit, job)]


def _reported_record(kit: AgentKit, job: ApplyJob) -> Callable:
    async def record_application(
        via: str, target: str, letter: str = "", screening: list[ScreeningPair] | None = None,
        already_applied: bool = False,
    ) -> str:
        """Записать отклик, который сайт подтвердил: aggregator или form, адрес страницы или формы, письмо, скрининг. В screening — каждый вопрос работодателя из формы и со страницы подтверждения вместе с данным ответом, по порядку; вопросов не было — пустой список. Повтор с тем же адресом дописывает скрининг. already_applied — сайт уже показывал «вы откликнулись»: отклик пишется без письма и без отправки."""
        letter_text = None if already_applied else (letter or None)
        return await _write(kit, job, _Report(via, target, letter_text, _lines(screening or [])))

    return record_application


def _confirmed_record(kit: AgentKit, job: ApplyJob) -> Callable:
    async def record_application(via: str, target: str, already_applied: bool = False) -> str:
        """Записать отклик, который сайт подтвердил: aggregator или form, адрес страницы или формы. Письмо и ответы на вопросы приложение берёт из подтверждённого человеком. Повтор с тем же адресом дописывает вопросы со страницы подтверждения. already_applied — сайт уже показывал «вы откликнулись»: отклик пишется без письма и без отправки."""
        letter, pairs = _confirmed_sent(job)
        return await _write(kit, job, _Report(via, target, None if already_applied else letter, _lines(pairs)))

    return record_application


async def _write(kit: AgentKit, job: ApplyJob, report: _Report) -> str:
    """Записать отклик или дописать скрининг к записанному в этой сессии."""
    if report.via not in _ALLOWED[job.way.method]:
        return "Этим способом отклик не пишется."
    # Записанный отклик дописывается, а не отказывает: окончательность здесь
    # нужна только «Закончить» — после него ничего не ушло и писать нечего.
    if isinstance(job.outcome, Dropped):
        return FINAL_ANSWER
    if isinstance(job.outcome, Applied):
        answer = await _append(kit, job.outcome.application_id, report.screening)
    else:
        answer = await _record(kit, job, _entry(job, report))
    job.unscreened.clear()
    return answer


def _entry(job: ApplyJob, report: _Report) -> ApplicationEntry:
    return ApplicationEntry(
        vacancy_id=job.vacancy_id, aggregator_id=job.way.aggregator_id,
        via=ApplicationVia(report.via), target=report.target, letter=report.letter,
        screening=report.screening,
    )


def _lines(screening: list[ScreeningPair]) -> list[tuple[bool, str]]:
    """Пара ложится двумя репликами ленты: вопрос работодателя, затем ответ человека."""
    return [line for pair in screening for line in ((False, pair["question"]), (True, pair["answer"]))]


def _confirmed_sent(job: ApplyJob) -> tuple[str | None, list[ScreeningPair]]:
    """Письмо и скрининг под подтверждением — то, что ушло, а не пересказ агента.

    Письмо — последний подтверждённый пункт-письмо; скрининг — прочие пункты,
    ещё не легшие в запись.
    """
    letter = next((item["value"] for item in reversed(job.confirmed.values())
                   if item["kind"] == "letter"), "")
    pairs = [{"question": item["label"], "answer": _answer(item)}
             for item in job.unscreened.values() if item["kind"] != "letter"]
    return letter or None, pairs


def _answer(item: dict) -> str:
    """Галочка в ленте — словом, как её прочтёт человек."""
    if item["kind"] == "check":
        return "да" if is_checked(item) else "нет"
    return item["value"]


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
