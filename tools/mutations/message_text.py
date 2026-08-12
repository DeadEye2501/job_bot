"""Поломки для текста сообщения `backend/message_text.py`.

Набор отпочковался от `helpers` заходом Д этапа 4 вместе с самим модулем:
гонять поломки надо против проверок своего предмета, а они разъехались по
трём файлам.
"""

# (файл, что заменить, на что заменить) — по одной осмысленной поломке.
MUTATIONS = [
    # extract_text: пропадает запасной вариант через caption
    (
        "backend/message_text.py",
        'return (msg.text or msg.caption or "").strip()',
        'return (msg.text or "").strip()',
    ),
    # _media_placeholder: ветка «Фото» никогда не срабатывает
    (
        "backend/message_text.py",
        'if getattr(msg, "photo", None):\r\n        return "[Фото]"',
        'if False:\r\n        return "[Фото]"',
    ),
    # _media_placeholder: ветка «Документ» никогда не срабатывает
    (
        "backend/message_text.py",
        'if getattr(msg, "document", None):\r\n        return "[Документ]"',
        'if False:\r\n        return "[Документ]"',
    ),
    # extract_dm_text: голосовое больше не распознаётся
    (
        "backend/message_text.py",
        'body = extract_text(msg)\r\n    if getattr(msg, "voice", None):',
        "body = extract_text(msg)\r\n    if False:",
    ),
    # extract_dm_text: подпись голосового теряется
    (
        "backend/message_text.py",
        'body = f"Голосовое сообщение: {body}" if body else "Голосовое сообщение"',
        'body = "Голосовое сообщение"',
    ),
    # extract_dm_text: перевёрнутая проверка родителя
    (
        "backend/message_text.py",
        "if parent is None:\r\n        return body",
        "if parent is not None:\r\n        return body",
    ),
    # extract_dm_text: переводы строк в цитате не схлопываются
    (
        "backend/message_text.py",
        'quote = quote.replace("\\n", " ").strip()',
        "quote = quote.strip()",
    ),
    # extract_dm_text: порог обрезки цитаты расширен на порядок
    (
        "backend/message_text.py",
        "if len(quote) > 80:",
        "if len(quote) > 800:",
    ),
    # extract_dm_text: пустое тело больше не даёт «голую» цитату
    (
        "backend/message_text.py",
        'return f"↪ {quote}\\n\\n{body}" if body else f"↪ {quote}"',
        'return f"↪ {quote}\\n\\n{body}"',
    ),
]
