"""Отклик письмом без агента: модель приложения пишет, сервер почты принимает,
отклик записывается."""

import asyncio
import logging
import smtplib

from adapters import smtp_mail
from adapters.smtp_mail import MailAccountConfig, OutgoingMail
from backend.agent.confirm import confirmed, text_item
from backend.agent.kit import AgentKit
from backend.agent.tools_applier import record_and_announce
from backend.agent.tools_letter import letter_ask
from backend.applying.resume_link import resume_for_letter
from backend.applying.result import GONE, Dropped, Missed, Outcome, delivered
from backend.domain.apply_order import Way
from backend.llm.agent_letter import write_letter
from backend.models import ApplicationVia
from backend.repository.applications import ApplicationEntry
from backend.repository.mail_account import get_mail_account

logger = logging.getLogger(__name__)


async def via_email(kit: AgentKit, vacancy_id: int, way: Way) -> Outcome:
    """Письмо от модели приложения, SMTP, запись — одним шагом: ушедшее и
    не записанное письмо дало бы второе на следующем отклике.

    Почта и резюме проверяются до письма: не с чем отправить — незачем ни
    писать, ни звать человека подтверждать. Резюме — файлом, а нет файла —
    ссылкой в конце письма."""
    account = await kit.read(get_mail_account)
    resume = await resume_for_letter(kit.pipeline)
    if account is None:
        return Missed("почта для откликов не настроена")
    if resume is None:
        return Missed("нет ни файла резюме, ни ссылки на него")
    ask = await letter_ask(kit, vacancy_id, None)
    if ask is None:
        return GONE
    letter, issues = await write_letter(ask, kit.pipeline.lm_client, kit.pipeline.lm_chat_model)
    if letter is None:
        return Missed(f"письмо не написано: {'; '.join(issues)}")
    # Тема тоже уходит работодателю: подтверждается вместе с письмом.
    kept = await confirmed(kit, vacancy_id, [text_item("Тема", letter.subject),
                                             text_item("", resume.under(letter.body))])
    if isinstance(kept, Dropped):
        return kept
    # Тема — одной строкой: перевод строки в заголовке письмо не соберёт.
    mail = OutgoingMail(way.target, " ".join(kept[0]["value"].split()), kept[1]["value"], resume.file)
    sending = asyncio.ensure_future(_send_and_record(kit, vacancy_id, account, mail))
    return await asyncio.shield(sending)


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
        letter=mail.body, letter_by="app", screening=[], simulated=simulated)), vacancy_id)
