"""Инструменты откликателя: своя вакансия, запись отклика на сайте и отклик письмом."""

import asyncio
import logging
import smtplib
from collections.abc import Callable
from dataclasses import dataclass

from adapters import smtp_mail
from adapters.smtp_mail import MailAccountConfig, OutgoingMail
from backend.agent.jobs import Applied, ApplyJob, Failed
from backend.agent.kit import AgentKit
from backend.domain.apply_order import VIA_AGGREGATOR, VIA_EMAIL, VIA_FORM
from backend.models import ApplicationVia
from backend.repository.applications import ApplicationEntry, append_screening, application_exists
from backend.repository.applications import record_application as store
from backend.repository.mail_account import get_mail_account
from backend.repository.vacancy_brief import describe_vacancy
from backend.repository.vacancy_contacts import has_contact

logger = logging.getLogger(__name__)

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
        if via not in _ALLOWED[job.method]:
            return "Этим способом отклик не пишется."
        lines = _lines(screening or [])
        if isinstance(job.outcome, Applied):
            return await _append(kit, job.outcome.application_id, lines)
        letter_text = None if already_applied else (letter or None)
        return await _record(kit, job, _entry(job, _Report(via, target, letter_text, lines)))

    async def send_email(address: str, subject: str, body: str) -> str:
        """Отправить письмо-отклик с резюме на адрес из контактов вакансии. Отклик записывается, когда сервер почты принял письмо."""
        # Тема — одной строкой: перевод строки в заголовке письмо не соберёт.
        return await _send_email(kit, job, _Report(VIA_EMAIL, address.strip(), body, []),
                                 " ".join(subject.split()))

    if job.method == VIA_EMAIL:
        return [vacancy, send_email]
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
        vacancy_id=job.vacancy_id, aggregator_id=job.aggregator_id,
        via=ApplicationVia(report.via), target=report.target, letter=report.letter,
        letter_by=job.letter_writer if report.letter else None,
        screening=report.screening, simulated=job.simulated,
    )


def _lines(screening: list[dict]) -> list[tuple[bool, str]]:
    return [(bool(x.get("from_us")), str(x.get("text", ""))) for x in screening if isinstance(x, dict)]


async def _record(kit: AgentKit, job: ApplyJob, entry: ApplicationEntry) -> str:
    application_id = await kit.written(lambda session: store(session, entry))
    job.outcome = Applied(application_id)
    kit.pipeline.fire_vacancies_changed()
    return "Отклик записан."


async def _append(kit: AgentKit, application_id: int, lines: list[tuple[bool, str]]) -> str:
    """Скрининг к отклику, уже записанному в этой сессии: вопросы со страницы
    подтверждения ложатся туда же, даже если её адрес другой."""
    await kit.written(lambda session: append_screening(session, application_id, lines))
    return "Скрининг дописан к записанному отклику."


async def _send_email(kit: AgentKit, job: ApplyJob, report: _Report, subject: str) -> str:
    """Письмо уходит только на контакт своей вакансии, один раз и с резюме;
    отклик записывается после того, как сервер его принял."""
    if isinstance(job.outcome, Applied):
        return "Отклик уже записан: второе письмо ушло бы тому же работодателю. Заверши работу."
    if not subject or not report.letter.strip():
        return "Нужны тема и текст письма — письмо не отправлено."
    async with kit.pipeline.session_factory() as session:
        if not await has_contact(session, job.vacancy_id, report.target):
            return "Адрес не из контактов вакансии — письмо не отправлено."
        if await application_exists(session, job.vacancy_id, report.target):
            return "Отклик на этот адрес уже отправлен."
        account = await get_mail_account(session)
    if account is None:
        job.outcome = Failed("почта для откликов не настроена")
        return "Почта для откликов не настроена."
    resume = kit.pipeline.cv_file()
    if resume is None:
        job.outcome = Failed("нет файла резюме")
        return "Нет файла резюме."
    # Отправка и запись — одним неразрывным шагом: погашенная между ними сессия
    # оставила бы ушедшее письмо без отклика, и следующий обход послал бы второе.
    # Задача лежит на задании: следующий способ ждёт её конца (`_one_way`).
    job.delivery = asyncio.ensure_future(_send_and_record(kit, job, report, OutgoingMail(
        report.target, subject, report.letter, resume), account))
    job.delivery.add_done_callback(_log_lost)
    return await asyncio.shield(job.delivery)


def _log_lost(delivery: asyncio.Task) -> None:
    """Сбой отправки или записи — в журнал: ждавшая сессия могла уже кончиться,
    и больше его никто не прочтёт."""
    if not delivery.cancelled() and delivery.exception() is not None:
        logger.error("письмо-отклик: сбой отправки или записи", exc_info=delivery.exception())


async def _send_and_record(kit: AgentKit, job: ApplyJob, report: _Report, mail: OutgoingMail,
                           account: MailAccountConfig) -> str:
    if not job.simulated:
        trouble = await _deliver(account, mail)
        if trouble is not None:
            job.outcome = Failed(trouble)
            return trouble
    return await _record(kit, job, _entry(job, report))


async def _deliver(account: MailAccountConfig, mail: OutgoingMail) -> str | None:
    """Отдать письмо серверу. Пусто — принял; иначе — почему нет.

    Зов через модуль, а не связанное имя: тест подменяет отправку на модуле.
    """
    try:
        await asyncio.to_thread(smtp_mail.send_mail, account, mail)
    except (smtplib.SMTPException, OSError) as error:
        logger.exception("письмо-отклик на %s не ушло", mail.to)
        return f"сервер почты не принял письмо: {error}"
    return None
