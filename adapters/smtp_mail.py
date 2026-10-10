"""Отправка письма по SMTP с вложением, под паролем приложения."""

import logging
import mimetypes
import smtplib
import ssl
from dataclasses import dataclass, field
from email.message import EmailMessage
from pathlib import Path

from backend.domain.mail_servers import STARTTLS_PORT

logger = logging.getLogger(__name__)

_TIMEOUT_SEC = 60


@dataclass(frozen=True)
class MailAccountConfig:
    address: str
    host: str
    port: int
    password: str = field(repr=False)


@dataclass(frozen=True)
class OutgoingMail:
    to: str
    subject: str
    body: str
    attachment: Path


def send_mail(account: MailAccountConfig, mail: OutgoingMail) -> None:
    """Отправить письмо. Ошибку сервера пробрасывает: отклик без письма не записывается.

    На порте 587 сервер ждёт STARTTLS, а не шифрования с порога: `SMTP_SSL`
    туда не подключится.
    """
    message = _message(account.address, mail)
    context = ssl.create_default_context()
    if account.port == STARTTLS_PORT:
        smtp = smtplib.SMTP(account.host, account.port, timeout=_TIMEOUT_SEC)
    else:
        smtp = smtplib.SMTP_SSL(account.host, account.port, context=context, timeout=_TIMEOUT_SEC)
    try:
        if account.port == STARTTLS_PORT:
            smtp.starttls(context=context)
        smtp.login(account.address, account.password)
        smtp.send_message(message)
    finally:
        _part(smtp)


def _part(smtp) -> None:
    """Попрощаться с сервером. Не `with`: его выход бросает на ответе, отличном
    от 221, — и письмо, которое сервер уже принял, сочлось бы неотправленным,
    а следующий способ отправил бы второй отклик."""
    try:
        smtp.quit()
    except (smtplib.SMTPException, OSError):
        logger.warning("сервер почты попрощался с ошибкой", exc_info=True)
        smtp.close()


def _message(sender: str, mail: OutgoingMail) -> EmailMessage:
    message = EmailMessage()
    message["From"], message["To"], message["Subject"] = sender, mail.to, mail.subject
    message.set_content(mail.body)
    kind = mimetypes.guess_type(mail.attachment.name)[0] or "application/octet-stream"
    main, sub = kind.split("/", 1)
    message.add_attachment(
        mail.attachment.read_bytes(), maintype=main, subtype=sub, filename=mail.attachment.name
    )
    return message
