import logging
import re

from pyrogram.errors import FloodWait


logger = logging.getLogger(__name__)


_TG_USERNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{4,31}$")
# Ник, набранный человеком, принимается и от четырёх символов: новым такие
# Telegram не выдаёт, но выданные до ужесточения работают, и собеседник с
# таким ником обычен. В объявлении о работе та же поблажка опасна — «Anna»
# там имя, а не ник, и разыскав по нему живую чужую учётную запись, отклик
# ушёл бы постороннему. Разница не в строгости, а в том, кто отвечает за
# написанное: за формой стоит человек, за объявлением никто.
_TG_TYPED_USERNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{3,31}$")
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


def _strip_link_prefixes(s: str) -> str:
    """Снять с записи всё, что стоит перед самим ником.

    Порядок обязателен: домен ищут в том, что осталось от схемы, а путь
    веб-просмотра — в том, что осталось от домена.

    `www.` снимается вместе с доменом, а не отдельной строкой до него: сам по
    себе он ничего не говорит, и снятый заранее превращал бы `www.jobsboard`
    в ник `jobsboard` — запись, которая ником не является вовсе.

    `s/` разбирается здесь, а не общим правилом хвоста: сам `s` числится
    служебным путём, и без этой строки `t.me/s/канал` отсеивался бы наравне
    с `t.me/c/12345`, то есть ссылка на канал считалась бы негодной.
    """
    for prefix in ("https://", "http://"):
        if s.startswith(prefix):
            s = s[len(prefix):]
    for host in ("t.me/", "telegram.me/", "www.t.me/", "www.telegram.me/"):
        if s.startswith(host):
            s = s[len(host):]
            if s.startswith("s/"):
                s = s[len("s/"):]
            break
    return s


def normalize_username(hr_contact: str | None, *, typed_by_a_person: bool = False) -> str | None:
    """Ник из записи контакта: голое написание или отсутствие.

    ``typed_by_a_person`` опускает нижнюю границу длины до четырёх — см.
    `_TG_TYPED_USERNAME_RE`. Своим доводом, а не отдельным объявлением,
    потому что различается только эта граница, а разбор ссылки, собачки и
    хвоста у обоих один.
    """
    if not hr_contact:
        return None
    s = _strip_link_prefixes(hr_contact.strip())
    s = s.lstrip("@").strip().rstrip("/")
    if "/" in s:
        s = s.split("/", 1)[0]
    if not s or s.startswith("+"):
        return None
    if s.lower() in _TG_RESERVED_PATHS:
        return None
    allowed = _TG_TYPED_USERNAME_RE if typed_by_a_person else _TG_USERNAME_RE
    if not allowed.match(s):
        return None
    return s


def typed_username(value) -> str | None:
    """Ник, введённый человеком в поле формы: пусто — отсутствие, негодное —
    отказ.

    Отличается от `normalize_username` тем, что различает «поле пустое» и
    «поле заполнено чем-то не тем». Первое законно — ник знают не про
    каждого HR; второе молча превратилось бы в отсутствие, и человек узнал
    бы об этом, только когда отправка перестала находить собеседника.

    Одна собачка считается пустым полем: её набирают первой и стирают
    вместе со всем остальным.

    Четырёхбуквенные ники здесь проходят, а в разборе объявления нет: за
    формой стоит человек, который написанное подтверждает.
    """
    if value is None:
        return None
    typed = str(value).strip().lstrip("@").strip()
    if not typed:
        return None
    handle = normalize_username(typed, typed_by_a_person=True)
    if handle is None:
        raise ValueError("ник не похож на телеграмовский")
    return handle


def telegram_peer(hr) -> int | str | None:
    """Адресат HR в Telegram: учётная запись, иначе ник, иначе ничего.

    Порядок важен: номер учётной записи не меняется, а ник человек
    меняет когда угодно — по старому письмо уйдёт чужому человеку или не
    уйдёт вовсе. Ничего — значит писать некуда; что делать дальше, решает
    зовущий.
    """
    return hr.telegram_user_id or hr.telegram_username


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
