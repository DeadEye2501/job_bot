from pathlib import Path

from pyrogram import Client
from pyrogram.types import User

from backend.runtime_settings import TgAccountConfig
from config import get_data_dir


SESSION_NAME = "job_bot"


def make_client(tg: TgAccountConfig) -> Client:
    """Build a pyrogram client from a runtime TG config.

    If ``session_string`` is set, runs in-memory (preferred — survives moving
    the app data dir). Otherwise falls back to a file-based session in the
    per-user data dir, expected to be populated on first interactive login.
    """
    if tg.session_string:
        return Client(
            name=SESSION_NAME,
            session_string=tg.session_string,
            api_id=tg.api_id,
            api_hash=tg.api_hash,
            in_memory=True,
        )
    sessions_dir = get_data_dir() / "sessions"
    sessions_dir.mkdir(exist_ok=True)
    return Client(
        name=SESSION_NAME,
        api_id=tg.api_id,
        api_hash=tg.api_hash,
        phone_number=tg.phone,
        password=tg.password or None,
        workdir=str(sessions_dir),
    )


async def check(client: Client) -> User:
    return await client.get_me()


import logging

_log = logging.getLogger(__name__)


# === DEV SAFETY LOCK =======================================================
# True блочит реальную отправку DM (только лог). Нужно для тестов, чтобы не
# спамить HR'ов случайно. Снимать только когда юзер сознательно готов
# выпустить бота в реальную работу.
SEND_LOCKED = True
# ==========================================================================


async def send_dm(
    client: Client,
    user: str | int,
    text: str,
    attachment: str | Path | None = None,
) -> None:
    if SEND_LOCKED:
        _log.warning(
            "send_dm: SEND_LOCKED=True — would have sent to %r"
            "%s (%d chars), suppressed",
            user,
            f" with attachment {attachment}" if attachment else "",
            len(text),
        )
        return
    if attachment is not None:
        await client.send_document(user, str(attachment), caption=text)
    else:
        await client.send_message(user, text)
