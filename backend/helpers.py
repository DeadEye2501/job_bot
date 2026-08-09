import logging
import re

from pyrogram.errors import FloodWait


logger = logging.getLogger(__name__)


_TG_USERNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{4,31}$")
_TG_RESERVED_PATHS = {"joinchat", "c", "s", "bot", "dl", "addstickers"}


def extract_text(msg) -> str:
    return (msg.text or msg.caption or "").strip()


def _media_placeholder(msg) -> str:
    if getattr(msg, "photo", None):
        return "[Фото]"
    if getattr(msg, "document", None):
        return "[Документ]"
    if getattr(msg, "sticker", None):
        return "[Стикер]"
    if getattr(msg, "video", None):
        return "[Видео]"
    if getattr(msg, "voice", None):
        return "[Голосовое]"
    if getattr(msg, "video_note", None):
        return "[Видеосообщение]"
    if getattr(msg, "animation", None):
        return "[GIF]"
    if getattr(msg, "audio", None):
        return "[Аудио]"
    return "[Сообщение]"


def extract_dm_text(msg) -> str:
    """Like extract_text, but prefixes the body with an inline reply quote
    when the message is a reply. The quote is short — first 80 chars of the
    parent text (or a media placeholder), prefixed with «↪». Keeps the chat
    UI free of separate reply rows / new DB columns.

    Voice-сообщения у Telegram приходят без text, но Pyrogram-у `Voice`
    разрешает caption — и НЕ попадают в `classify_media` (мы их не качаем).
    Без подмены DB-row сохраняется с text="" (если caption нет) и в UI
    рендерится пустой бабл; либо с голым текстом caption — теряется сам
    факт, что это голосовое. Префиксим всегда, когда есть `voice`.
    """
    body = extract_text(msg)
    if getattr(msg, "voice", None):
        body = f"Голосовое сообщение: {body}" if body else "Голосовое сообщение"
    parent = getattr(msg, "reply_to_message", None)
    if parent is None:
        return body
    quote = extract_text(parent) or _media_placeholder(parent)
    quote = quote.replace("\n", " ").strip()
    if len(quote) > 80:
        quote = quote[:79].rstrip() + "…"
    return f"↪ {quote}\n\n{body}" if body else f"↪ {quote}"


def normalize_username(hr_contact: str | None) -> str | None:
    if not hr_contact:
        return None
    s = hr_contact.strip()
    for prefix in ("https://", "http://"):
        if s.startswith(prefix):
            s = s[len(prefix):]
    if s.startswith("t.me/"):
        s = s[len("t.me/"):]
    s = s.lstrip("@").strip().rstrip("/")
    if "/" in s:
        s = s.split("/", 1)[0]
    if not s or s.startswith("+"):
        return None
    if s.lower() in _TG_RESERVED_PATHS:
        return None
    if not _TG_USERNAME_RE.match(s):
        return None
    return s


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
    except Exception as e:
        logger.warning(
            "fetch_telegram_avatar: failed: %s: %s", type(e).__name__, e
        )
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
    except Exception as e:
        logger.warning(
            "resolve_hr_telegram: failed for %r: %s: %s",
            hr_contact,
            type(e).__name__,
            e,
        )
        return None

    if user is None:
        return None
    if getattr(user, "is_bot", False) or getattr(user, "is_deleted", False):
        return None
    return user
