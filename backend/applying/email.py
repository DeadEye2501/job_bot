"""Отклик письмом без агента: письмо готовое или от модели приложения, сервер
почты принимает, отклик записывается."""

import asyncio
import logging
import smtplib

from adapters import smtp_mail
from adapters.smtp_mail import MailAccountConfig, OutgoingMail
from backend.agent.confirm import confirmed, text_item
from backend.agent.kit import AgentKit
from backend.agent.tools_applier import record_and_announce
from backend.agent.tools_letter import letter_ask
from backend.applying.result import GONE, Dropped, Missed, Outcome, delivered
from backend.domain.apply_order import Way
from backend.domain.letter_choice import ready_letter
from backend.llm.agent_letter import Letter, write_letter
from backend.llm.letter_subject import letter_subject
from backend.models import ApplicationVia, Vacancy
from backend.repository.applications import ApplicationEntry
from backend.repository.cover_letters import get_letters
from backend.repository.mail_account import get_mail_account
from backend.repository.profile_languages import read_reply_language

logger = logging.getLogger(__name__)


async def via_email(kit: AgentKit, vacancy_id: int, way: Way) -> Outcome:
    """Готовое письмо человека или письмо модели приложения, SMTP, запись — одним шагом: ушедшее и
    не записанное письмо дало бы второе на следующем отклике.

    Почта и резюме проверяются до письма: не с чем отправить — незачем ни
    писать, ни звать человека подтверждать. Резюме — файлом, а нет файла —
    ссылкой в конце письма."""
    account = await kit.read(get_mail_account)
    language = await kit.read(lambda session: read_reply_language(session, vacancy_id))
    resume = await kit.read(lambda session: kit.reply_resume(session, language))
    if account is None:
        return Missed("почта для откликов не настроена")
    if resume is None:
        return Missed("нет ни файла резюме, ни ссылки на него")
    letter = await _ready(kit, vacancy_id, language)
    if letter is None:
        ask = await letter_ask(kit, vacancy_id, language, None)
        if ask is None:
            return GONE
        letter, issues = await write_letter(ask, kit.pipeline.lm_client, kit.pipeline.lm_chat_model)
        if letter is None:
            return Missed(f"письмо не написано: {'; '.join(issues)}")
    # Тема тоже уходит работодателю: подтверждается вместе с письмом.
    kept = await confirmed(kit, vacancy_id, [text_item("Тема", "text", letter.subject),
                                             text_item("Текст", "letter", resume.under(letter.body))])
    if isinstance(kept, Dropped):
        return kept
    # Тема — одной строкой: перевод строки в заголовке письмо не соберёт.
    mail = OutgoingMail(way.target, " ".join(kept[0]["value"].split()), kept[1]["value"], resume.file)
    sending = asyncio.ensure_future(_send_and_record(kit, vacancy_id, account, mail))
    return await asyncio.shield(sending)


async def _ready(kit: AgentKit, vacancy_id: int, language: str) -> Letter | None:
    """Полное готовое письмо человека с темой по шаблону; писем нет — пусто.

    Предела у почты нет, и короткое письмо берётся, только если полного нет.
    Сверку фактов готовое письмо не проходит: его написал сам человек. Анкета
    для модели здесь не собирается: письмо уже есть, а теме нужно одно название.
    Удалённая вакансия — тоже пусто: её отбивает путь письма модели.
    """
    async with kit.pipeline.session_factory() as session:
        body = ready_letter(await get_letters(session), language, None)
        vacancy = await session.get(Vacancy, vacancy_id) if body is not None else None
    if vacancy is None:
        return None
    pipeline = kit.pipeline
    subject = await letter_subject(vacancy.title or "", language, pipeline.lm_client,
                                   pipeline.lm_chat_model)
    return Letter(subject, body)


async def _send_and_record(kit: AgentKit, vacancy_id: int, account: MailAccountConfig,
                           mail: OutgoingMail) -> Outcome:
    simulated = kit.pipeline.rs.send_locked
    if not simulated:
        try:
            # Зов через модуль, а не связанное имя: тест подменяет отправку на модуле.
            await asyncio.to_thread(smtp_mail.send_mail, account, mail)
        # ValueError — адрес со знаком, которого заголовок письма не допускает.
        except (smtplib.SMTPException, OSError, ValueError) as error:
            logger.exception("письмо-отклик на %s не ушло", mail.to)
            return Missed(f"сервер почты не принял письмо: {error}")
    return await delivered(record_and_announce(kit, ApplicationEntry(
        vacancy_id=vacancy_id, aggregator_id=None, via=ApplicationVia.EMAIL, target=mail.to,
        letter=mail.body, screening=[])), vacancy_id)
