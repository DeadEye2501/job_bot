"""Текст сообщения Telegram в том виде, в каком его показывает окно.

Отличается от `backend/bot/media.py` тем, что тот решает, что мы храним, а
здесь решают, что человек прочтёт: цитата ответа, подпись вложения, слово
вместо голосового.
"""


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
