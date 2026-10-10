"""Почта для откликов письмом: одна строка, пароль шифром."""

from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from adapters.smtp_mail import MailAccountConfig
from backend.crypto import decrypt_or_none, encrypt_str
from backend.log_secrets import remember_secret
from backend.models import MailAccount

_SSL_PORT = 465
_STARTTLS_PORT = 587
_GMAIL = ("smtp.gmail.com", _SSL_PORT)
_YANDEX = ("smtp.yandex.ru", _SSL_PORT)
_MAIL_RU = ("smtp.mail.ru", _SSL_PORT)
_OUTLOOK = ("smtp.office365.com", _STARTTLS_PORT)
_KNOWN_SERVERS = {
    "gmail.com": _GMAIL, "googlemail.com": _GMAIL,
    "yandex.ru": _YANDEX, "ya.ru": _YANDEX, "yandex.com": _YANDEX,
    "mail.ru": _MAIL_RU, "inbox.ru": _MAIL_RU, "list.ru": _MAIL_RU, "bk.ru": _MAIL_RU,
    "outlook.com": _OUTLOOK, "hotmail.com": _OUTLOOK, "live.com": _OUTLOOK,
}
"""Сервер популярной почты по домену адреса: человеку незачем искать его в справке."""


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


def known_server(address: str | None) -> tuple[str, int] | None:
    """Сервер и порт популярной почты по домену адреса; незнакомой — пусто."""
    return _KNOWN_SERVERS.get((address or "").rpartition("@")[2].lower())


def _server(address: str | None, host: str | None, port: int | None) -> tuple[str | None, int | None]:
    if not (host or "").strip():
        return known_server(address) or (None, None)
    return host.strip(), port or _SSL_PORT
