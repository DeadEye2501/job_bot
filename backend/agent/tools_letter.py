"""Инструмент письма для отклика: пишет приложение или сверяется письмо агента."""

from collections.abc import Callable

from backend.agent.jobs import ApplyJob
from backend.agent.kit import AgentKit
from backend.llm.agent_letter import Letter, LetterAsk, check_letter, write_letter
from backend.models import Vacancy
from backend.repository.profile_languages import read_reply_language

CHECKS_ALLOWED = 2
"""Сколько раз проверка второй моделью смотрит предложение агента — письмо или
раскладку страницы резюме: спор сверх этого не сходится, а стоит вызовов."""

_ENOUGH = "отбито дважды: отправляй без письма, если поле необязательное, иначе report_failure"


def letter_tools(kit: AgentKit, job: ApplyJob) -> list[Callable]:
    """Инструмент письма своей вакансии; кто пишет письмо, задаёт `job.letter_writer`."""

    async def letter(limit: int = 0, subject: str = "", body: str = "") -> str:
        """Письмо для отклика на языке отклика из задания; limit — предел знаков поля, 0 — без предела. Если письмо пишешь ты — передай subject и body на сверку."""
        if job.letter_checks >= CHECKS_ALLOWED:
            return _ENOUGH
        if job.letter_writer == "agent" and not body.strip():
            return "Письмо пишешь ты: передай subject и body, приложение сверит их с анкетой."
        ask = await letter_ask(kit, job.vacancy_id, limit or None)
        if ask is None:
            return "Вакансия удалена."
        if job.letter_writer == "agent":
            return await _checked(kit, job, ask, Letter(subject.strip(), body.strip()))
        return await _written(kit, job, ask)

    return [letter]


async def letter_ask(kit: AgentKit, vacancy_id: int, limit: int | None) -> LetterAsk | None:
    """Что нужно модели для письма: анкета, вакансия и решённый язык отклика;
    удалённая вакансия — пусто."""
    async with kit.pipeline.session_factory() as session:
        vacancy = await session.get(Vacancy, vacancy_id)
        if vacancy is None:
            return None
        profile = await kit.profile_text(session)
        language = await read_reply_language(session, vacancy.language)
    return LetterAsk(profile_text=profile, title=vacancy.title or "", vacancy_text=vacancy.raw_text or "",
                     language=language, limit=limit)


async def _written(kit: AgentKit, job: ApplyJob, ask: LetterAsk) -> str:
    """Одна попытка приложения; второй зов `letter` в той же сессии — разрешённый повтор."""
    written, issues = await write_letter(ask, kit.pipeline.lm_client, kit.pipeline.lm_chat_model)
    if written is None:
        job.letter_checks += 1
        return f"письмо не написано: {'; '.join(issues)}"
    return f"Тема: {written.subject}\n\nПисьмо:\n{written.body}"


async def _checked(kit: AgentKit, job: ApplyJob, ask: LetterAsk, own: Letter) -> str:
    ok, issues = await check_letter(ask, own, kit.pipeline.lm_client, kit.pipeline.lm_chat_model)
    if ok:
        return "письмо принято"
    job.letter_checks += 1
    return f"письмо отбито: {'; '.join(issues)}"
