"""Отклик письмом без агента: модель приложения пишет, сервер почты принимает,
отклик записывается."""

import asyncio
import logging
import smtplib

from adapters import smtp_mail
from adapters.smtp_mail import OutgoingMail
from backend.agent.kit import AgentKit
from backend.agent.tools_applier import record_and_announce
from backend.agent.tools_letter import letter_ask
from backend.applying.result import GONE, Missed, Outcome, delivered
from backend.domain.apply_order import Way
from backend.llm.agent_letter import Letter, write_letter
from backend.models import ApplicationVia
from backend.repository.applications import ApplicationEntry
from backend.repository.mail_account import get_mail_account

logger = logging.getLogger(__name__)


async def via_email(kit: AgentKit, vacancy_id: int, way: Way) -> Outcome:
    """Письмо от модели приложения, SMTP, запись — одним шагом: ушедшее и
    не записанное письмо дало бы второе на следующем отклике."""
    ask = await letter_ask(kit, vacancy_id, "язык текста вакансии", None)
    if ask is None:
        return GONE
    letter, issues = await write_letter(ask, kit.pipeline.lm_client, kit.pipeline.lm_chat_model)
    if letter is None:
        return Missed(f"письмо не написано: {'; '.join(issues)}")
    sending = asyncio.ensure_future(_send_and_record(kit, vacancy_id, way, letter))
    return await asyncio.shield(sending)


async def _send_and_record(kit: AgentKit, vacancy_id: int, way: Way, letter: Letter) -> Outcome:
    async with kit.pipeline.session_factory() as session:
        account = await get_mail_account(session)
    resume = kit.pipeline.cv_file()
    if account is None:
        return Missed("почта для откликов не настроена")
    if resume is None:
        return Missed("нет файла резюме")
    simulated = kit.pipeline.rs.send_locked
    if not simulated:
        # Тема — одной строкой: перевод строки в заголовке письмо не соберёт.
        mail = OutgoingMail(way.target, " ".join(letter.subject.split()), letter.body, resume)
        try:
            # Зов через модуль, а не связанное имя: тест подменяет отправку на модуле.
            await asyncio.to_thread(smtp_mail.send_mail, account, mail)
        # ValueError — адрес со знаком, которого заголовок письма не допускает.
        except (smtplib.SMTPException, OSError, ValueError) as error:
            logger.exception("письмо-отклик на %s не ушло", way.target)
            return Missed(f"сервер почты не принял письмо: {error}")
    return await delivered(record_and_announce(kit, ApplicationEntry(
        vacancy_id=vacancy_id, aggregator_id=None, via=ApplicationVia.EMAIL, target=way.target,
        letter=letter.body, letter_by="app", screening=[], simulated=simulated)), vacancy_id)
