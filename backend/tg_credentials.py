"""Учётная запись Telegram: от строки в базе до следа в журнале."""

import logging
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.crypto import decrypt_or_none, encrypt_bytes, encrypt_str
from backend.models import TgAccount


logger = logging.getLogger(__name__)


def mask_phone(phone: str | None) -> str:
    """Безопасное представление phone для логов: показывает только last4
    для нормальных номеров (>=7 цифр), иначе полностью маскирует.
    Возвращает строку всегда, чтобы можно было передавать в %s без if'ов.
    """
    if not phone:
        return "***"
    if len(phone) < 7:
        return "***"
    return f"***{phone[-4:]}"


@dataclass(frozen=True)
class TgAccountConfig:
    api_id: int
    # Sensitive fields hidden from repr() so accidental logging never leaks them.
    api_hash: str = field(repr=False)
    phone: str
    password: str = field(repr=False)  # 2FA password; "" if none
    session_string: str | None = field(repr=False)  # pyrogram session; None pre-login


def log_tg_updated(
    api_id: int, phone: str, password: str, session_string: str | None
) -> None:
    """След смены учётной записи Telegram — без самих секретов.

    Номер пишется хвостом, чтобы мобильный не утекал в журнал открытым.
    Отпечаток приложения в журнал не идёт вовсе, а про пароль и строку
    сеанса говорится только «есть или нет».
    """
    logger.info(
        "Telegram credentials updated (api_id=%d, phone=%s, has_password=%s, has_session=%s)",
        api_id,
        mask_phone(phone),
        bool(password),
        session_string is not None,
    )


async def tg_row(session: AsyncSession) -> TgAccount | None:
    """Единственная строка учётной записи Telegram, если она заведена."""
    return (await session.scalars(select(TgAccount))).first()


def from_tg_row(row: TgAccount) -> TgAccountConfig | None:
    """Учётные данные Telegram из строки базы; `None`, если их нет.

    Нечитаемый шифротекст — тоже «нет», по причине из `decrypt_or_none`.
    """
    if row.api_id is None or not row.api_hash_encrypted or not row.phone:
        return None
    opened = []
    for ciphertext, what in (
        (row.api_hash_encrypted, "Telegram api_hash"),
        (row.password_encrypted, "Telegram password"),
        (row.session_blob_encrypted, "Telegram session"),
    ):
        # Один нечитаемый секрет — и вся запись «не настроена»: остальные
        # шифрованы тем же ключом, и читать их — множить следы одной беды.
        plain = decrypt_or_none(ciphertext, what)
        if plain is None:
            return None
        opened.append(plain)
    api_hash, password, session = opened
    return TgAccountConfig(
        api_id=row.api_id, api_hash=api_hash, phone=row.phone,
        password=password, session_string=session or None,
    )


def fill_tg_row(row: TgAccount, creds: TgAccountConfig) -> None:
    """Переписать строку учётной записи присланным, секреты — шифротекстом.

    Пустой пароль и пустая строка сеанса стирают записанный секрет: так
    человека и разлогинивают.
    """
    row.api_id = creds.api_id
    row.api_hash_encrypted = encrypt_str(creds.api_hash)
    row.phone = creds.phone
    row.password_encrypted = encrypt_str(creds.password) if creds.password else None
    row.session_blob_encrypted = (
        encrypt_bytes(creds.session_string.encode("utf-8"))
        if creds.session_string is not None
        else None
    )
