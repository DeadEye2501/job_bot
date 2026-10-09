"""Почта для откликов письмом: одна строка, пароль шифром."""

from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from adapters.smtp_mail import MailAccountConfig
from backend.crypto import decrypt_or_none, encrypt_str
from backend.log_secrets import remember_secret
from backend.models import MailAccount

_SSL_PORT = 465
_GMAIL = ("smtp.gmail.com", _SSL_PORT)
_GMAIL_DOMAINS = ("@gmail.com", "@googlemail.com")


@dataclass(frozen=True)
class MailSettings:
    address: str
    password: str | None = field(repr=False)
    host: str | None
    port: int | None


async def get_mail_account(session: AsyncSession) -> MailAccountConfig | None:
    """Почта, готовая к отправке, или пусто: без адреса, пароля или сервера писать нечем.

    `decrypt_or_none` отдаёт `""` за пустой секрет и `None` за нечитаемый; для
    почты оба значат одно — пароля нет.
    """
    row = await session.get(MailAccount, 1)
    if row is None or not row.address or not row.password_encrypted:
        return None
    if not row.smtp_host or not row.smtp_port:
        return None
    password = decrypt_or_none(row.password_encrypted, "mail password")
    if not password:
        return None
    remember_secret(password)
    return MailAccountConfig(row.address, row.smtp_host, row.smtp_port, password)


async def save_mail_account(session: AsyncSession, settings: MailSettings) -> None:
    """Записать почту. Пустой пароль — оставить прежний; у Gmail сервер подставляется сам."""
    row = await session.get(MailAccount, 1) or MailAccount(id=1)
    session.add(row)
    row.address = settings.address.strip() or None
    if settings.password:
        remember_secret(settings.password)
        row.password_encrypted = encrypt_str(settings.password)
    row.smtp_host, row.smtp_port = _server(row.address, settings.host, settings.port)


def _server(address: str | None, host: str | None, port: int | None) -> tuple[str | None, int | None]:
    if not (host or "").strip():
        return _GMAIL if address and address.lower().endswith(_GMAIL_DOMAINS) else (None, None)
    return host.strip(), port or _SSL_PORT
