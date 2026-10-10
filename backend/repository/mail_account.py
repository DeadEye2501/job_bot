"""Почта для откликов письмом: одна строка, пароль шифром."""

from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from adapters.smtp_mail import MailAccountConfig
from backend.crypto import decrypt_or_none, encrypt_str
from backend.domain.mail_servers import SSL_PORT, known_server
from backend.log_secrets import remember_secret
from backend.models import MailAccount


@dataclass(frozen=True)
class MailSettings:
    address: str
    password: str | None = field(repr=False)
    host: str | None
    port: int | None


async def get_mail_account(session: AsyncSession) -> MailAccountConfig | None:
    """Почта, готовая к отправке, или пусто: без адреса, пароля или сервера писать нечем."""
    saved = await read_mail_account(session)
    if saved is None or not (saved.address and saved.password and saved.host and saved.port):
        return None
    return MailAccountConfig(saved.address, saved.host, saved.port, saved.password)


async def read_mail_account(session: AsyncSession) -> MailSettings | None:
    """Почта для экрана настроек — как записана, с паролем открытым текстом.

    Пароль окну отдаётся, как ключи моделей: подключённая почта открывается с
    ним точками, и глазом его можно показать. Нечитаемый шифр — пустой пароль:
    его вписывают заново.
    """
    row = await session.get(MailAccount, 1)
    if row is None:
        return None
    password = decrypt_or_none(row.password_encrypted, "mail password") or ""
    if password:
        remember_secret(password)
    return MailSettings(row.address or "", password, row.smtp_host, row.smtp_port)


async def save_mail_account(session: AsyncSession, settings: MailSettings) -> None:
    """Записать почту. Пустой пароль — оставить прежний; у популярной почты сервер подставляется сам."""
    row = await session.get(MailAccount, 1) or MailAccount(id=1)
    session.add(row)
    row.address = settings.address.strip() or None
    if settings.password:
        remember_secret(settings.password)
        row.password_encrypted = encrypt_str(settings.password)
    row.smtp_host, row.smtp_port = _server(row.address, settings.host, settings.port)


def _server(address: str | None, host: str | None, port: int | None) -> tuple[str | None, int | None]:
    """Сервер популярной почты берётся по адресу, даже если прислан другой: окно шлёт
    почту целиком, и сервер, подставленный прежнему адресу, иначе пережил бы смену адреса."""
    known = known_server(address)
    if known:
        return known
    host = (host or "").strip()
    if not host:
        return None, None
    return host, port or SSL_PORT
