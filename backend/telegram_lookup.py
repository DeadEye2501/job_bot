"""Что берётся у Telegram по дороге, а не ради самого похода.

Картинка собеседника, картинка с названием канала, сам собеседник по
записанному контакту. От `adapters/telegram.py` отличается тем, что тот
объявляет разговор с Telegram — клиента, отправку, запор, — а здесь стоят
ответы на вопросы бэкенда, и правило ответа у всех троих одно: беда даёт
пустоту. Спрашивают их попутно, и уронить из-за неотданной картинки разбор
объявления значило бы менять важное на украшение.

`read_channel_metadata` своего перехвата не имеет нарочно: сама она в сеть не
ходит, а решает, спрашивать ли картинку, — перехват стоит у того, кто ходит.
"""

import logging

from pyrogram.errors import FloodWait

from backend.domain.telegram_identity import normalize_username

logger = logging.getLogger(__name__)


async def read_channel_metadata(
    client, chat, *, current_avatar: bytes | None = None
) -> tuple[str | None, bytes | None]:
    """Название и картинка канала из ответа Telegram.

    Спрашивают об этом двое — заведение канала из окна и сводка обновления
    перед обходом.

    **Название отдаётся как есть,** и что с ним делать, решает зовущий: у
    заведения строка новая и перебивать нечего, сводка сравнивает с прежним.

    **Картинка берётся только в пустое место,** и это правило объявления, а не
    зовущего: однажды взятая остаётся, иначе свежую затирала бы устаревшая с
    любого запоздавшего пути. Отсюда и довод `current_avatar` — без него
    сводка качала бы картинку на каждом обходе, чтобы тут же её выбросить.
    """
    title = getattr(chat, "title", None)
    if current_avatar is not None:
        return title, None
    return title, await fetch_telegram_avatar(client, chat)


async def fetch_telegram_avatar(client, entity) -> bytes | None:
    """Download the small profile photo from a Pyrogram User or Chat.

    Duck-typed on ``.photo`` — both ``pyrogram.types.User`` and
    ``pyrogram.types.Chat`` carry the same ``ChatPhoto`` shape with
    ``small_file_id`` / ``big_file_id``, so the same fetch path covers
    HR contacts and Telegram channels alike.
    """
    photo = getattr(entity, "photo", None)
    if photo is None:
        return None
    file_id = getattr(photo, "small_file_id", None) or getattr(photo, "big_file_id", None)
    if not file_id:
        return None
    try:
        buf = await client.download_media(file_id, in_memory=True)
    except FloodWait as e:
        logger.warning(
            "fetch_telegram_avatar: FloodWait %ds, skipping", getattr(e, "value", "?")
        )
        return None
    except Exception:
        logger.exception("fetch_telegram_avatar: failed")
        return None
    if buf is None:
        return None
    return buf.getvalue()


async def resolve_hr_telegram(client, hr_contact: str):
    username = normalize_username(hr_contact)
    if not username:
        return None
    try:
        user = await client.get_users(username)
    except FloodWait as e:
        logger.warning(
            "resolve_hr_telegram: FloodWait %ds, skipping", getattr(e, "value", "?")
        )
        return None
    except Exception:
        logger.exception("resolve_hr_telegram: failed for %r", hr_contact)
        return None

    if user is None:
        return None
    if getattr(user, "is_bot", False) or getattr(user, "is_deleted", False):
        return None
    return user
