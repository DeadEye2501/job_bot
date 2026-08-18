"""Текст сообщения Telegram в том виде, в каком его читают.

Отличается от `backend/bot/media.py` тем, что тот решает, что мы храним, а
здесь решают, что прочтут: цитата ответа, подпись вложения, слово вместо
голосового, адрес спрятанной ссылки.

Читателей двое, и текст им нужен разный. Окно и разбор переписки читают то,
что видно человеку на экране (`extract_text`, `extract_dm_text`). Разбор
объявления читает то же плюс адреса ссылок (`extract_post_text`): по ним
откликаются, а на экране их не видно вовсе.
"""

from pyrogram.parser.utils import add_surrogates, remove_surrogates


def extract_text(msg) -> str:
    return (msg.text or msg.caption or "").strip()


def _with_link_addresses(text: str, entities) -> str:
    """Дописать за каждой спрятанной ссылкой её адрес в скобках.

    Отсчёт мест Telegram ведёт в единицах UTF-16, а python — в знаках, и на
    любом смайле они расходятся. Поэтому вставка идёт по строке, переведённой
    в тот же счёт, — теми же орудиями, какими это делает сам Pyrogram.

    Идём с конца: вставка сдвигает всё, что правее, и места, снятые заранее,
    после первой же врезки перестали бы указывать куда надо.

    Адрес есть только у ссылки, спрятанной под словами. У набранного в тексте
    адреса своего поля нет — дописывать нечего, и второй раз он не появится.
    """
    surrogated = add_surrogates(text)
    ends = sorted(
        ((e.offset + e.length, e.url) for e in entities if e.url),
        reverse=True,
    )
    for end, url in ends:
        surrogated = f"{surrogated[:end]} ({url}){surrogated[end:]}"
    return remove_surrogates(surrogated)


def extract_post_text(msg) -> str:
    """Текст объявления вместе с адресами спрятанных в нём ссылок.

    Объявления сплошь и рядом прячут способ отклика под словом — «контакты в
    описании», «Откликнуться», — и в тексте от него остаётся одна подпись.
    Разбору по такой подписи откликаться некуда, и он честно выбрасывал её
    (см. `_way_to_apply` в `backend/llm/vacancy.py`): контакт вроде бы есть, а
    адреса нет. Здесь адрес возвращается на место — рядом со своими словами, а
    не списком в хвосте: разбору важно, к чему ссылка относится.

    Переписки это не касается: там читают то, что видно на экране.
    """
    body = msg.text or msg.caption or ""
    entities = (msg.entities if msg.text else msg.caption_entities) or []
    return _with_link_addresses(body, entities).strip()


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
