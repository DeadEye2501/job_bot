"""Сборка клиента Telegram и отправка письма его руками.

Единственным домом знания о Pyrogram модуль не является, и делать вид не
стоит: клиента ввозят ещё семеро — бот, обработчики, вход по коду, чтение
метаданных, догон переписки. Здесь собрано то, что зовут все: как клиент
собирается и как через него уходит письмо.

`SEND_LOCKED` живёт тут же, потому что читает его отсюда общий заслон
(`bot/can_send`) — а заслон спрашивают все дороги отправки, включая переписку
из окна, которая письмо шлёт своим зовом мимо `send_dm`. Проверка в самом
`send_dm` — второй рубеж, на случай дороги, заслон не спросившей.
"""

from pathlib import Path

from pyrogram import Client

from backend.runtime_settings import TgAccountConfig
from config import get_data_dir


SESSIONS_DIR = get_data_dir() / "sessions"
"""Папка, в которой Pyrogram держит файл сеанса.

Объявлена здесь, а не у зовущего: имя знает и снос данных, и оболочка, что
ищет осиротевшие файлы сеанса.
"""

SESSION_NAME = "job_bot"


def make_client(tg: TgAccountConfig) -> Client:
    """Build a pyrogram client from a runtime TG config.

    If ``session_string`` is set, runs in-memory (preferred — survives moving
    the app data dir). Otherwise falls back to a file-based session in the
    per-user data dir, expected to be populated on first interactive login.
    """
    # ``sleep_threshold=60``: Pyrogram сам ждёт и ретраит FloodWait короче
    # 60с (default 10с) — закрывает пиковые TG-rate-limit'ы во время
    # batch-параллельного добора пропущенных сообщений без промахов.
    if tg.session_string:
        return Client(
            name=SESSION_NAME,
            session_string=tg.session_string,
            api_id=tg.api_id,
            api_hash=tg.api_hash,
            in_memory=True,
            sleep_threshold=60,
        )
    sessions_dir = SESSIONS_DIR
    sessions_dir.mkdir(exist_ok=True)
    return Client(
        name=SESSION_NAME,
        api_id=tg.api_id,
        api_hash=tg.api_hash,
        phone_number=tg.phone,
        password=tg.password or None,
        workdir=str(sessions_dir),
        sleep_threshold=60,
    )


import logging

_log = logging.getLogger(__name__)


# Запор боевой отправки: `True` — письмо не уходит. Хозяин запора не здесь, а в
# настройке `send_locked`, и в базе она по умолчанию `true`; сюда значение
# переписывают на старте бота и при правке настроек, чтобы горячий путь отправки
# не ходил за ним в базу. Поэтому `False` в объявлении значит «до первой
# синхронизации», а не «отправка разрешена».
# Спрашивают его трое и делают разное: общий заслон (`bot/can_send`) отвечает
# окну отказом, `send_dm` под запором пишет в журнал вместо отправки, а отклик
# (`flows/apply`) этим же словом отличает в ленте отправленное от показанного.
SEND_LOCKED = False


async def send_dm(
    client: Client,
    user: str | int,
    text: str,
    attachment: str | Path | None = None,
) -> int | None:
    """Отправляет DM. Возвращает Telegram message_id ответа Pyrogram'а,
    либо None если отправка заглушена SEND_LOCKED — caller использует id
    для записи в Message.tg_message_id (закрывает UNIQUE-дыру с NULL'ами
    для outgoing-row'ов)."""
    if SEND_LOCKED:
        _log.warning(
            "send_dm: SEND_LOCKED=True — would have sent to %r"
            "%s (%d chars), suppressed",
            user,
            f" with attachment {attachment}" if attachment else "",
            len(text),
        )
        return None
    if attachment is not None:
        msg = await client.send_document(user, str(attachment), caption=text)
    else:
        msg = await client.send_message(user, text)
    return getattr(msg, "id", None)
