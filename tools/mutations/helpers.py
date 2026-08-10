"""Поломки для `backend/helpers.py`."""

# (файл, что заменить, на что заменить) — по одной осмысленной поломке.
MUTATIONS = [
    # typed_username: негодный ник молча становится отсутствием
    (
        "backend/helpers.py",
        "    if handle is None:\r\n"
        '        raise ValueError("ник не похож на телеграмовский")\r\n',
        "",
    ),
    # typed_username: одна собачка перестаёт считаться пустым полем
    (
        "backend/helpers.py",
        '    typed = str(value).strip().lstrip("@").strip()',
        "    typed = str(value).strip()",
    ),
    # typed_username: ник из формы разбирают правилом объявления
    (
        "backend/helpers.py",
        "    handle = normalize_username(typed, typed_by_a_person=True)",
        "    handle = normalize_username(typed)",
    ),
    # normalize_username: поблажка по длине достаётся и разбору объявления
    (
        "backend/helpers.py",
        "    allowed = _TG_TYPED_USERNAME_RE if typed_by_a_person else _TG_USERNAME_RE",
        "    allowed = _TG_TYPED_USERNAME_RE",
    ),
    # extract_text: пропадает запасной вариант через caption
    (
        "backend/helpers.py",
        'return (msg.text or msg.caption or "").strip()',
        'return (msg.text or "").strip()',
    ),
    # _media_placeholder: ветка «Фото» никогда не срабатывает
    (
        "backend/helpers.py",
        'if getattr(msg, "photo", None):\r\n        return "[Фото]"',
        'if False:\r\n        return "[Фото]"',
    ),
    # _media_placeholder: ветка «Документ» никогда не срабатывает
    (
        "backend/helpers.py",
        'if getattr(msg, "document", None):\r\n        return "[Документ]"',
        'if False:\r\n        return "[Документ]"',
    ),
    # extract_dm_text: голосовое больше не распознаётся
    (
        "backend/helpers.py",
        'body = extract_text(msg)\r\n    if getattr(msg, "voice", None):',
        "body = extract_text(msg)\r\n    if False:",
    ),
    # extract_dm_text: подпись голосового теряется
    (
        "backend/helpers.py",
        'body = f"Голосовое сообщение: {body}" if body else "Голосовое сообщение"',
        'body = "Голосовое сообщение"',
    ),
    # extract_dm_text: перевёрнутая проверка родителя
    (
        "backend/helpers.py",
        "if parent is None:\r\n        return body",
        "if parent is not None:\r\n        return body",
    ),
    # extract_dm_text: переводы строк в цитате не схлопываются
    (
        "backend/helpers.py",
        'quote = quote.replace("\\n", " ").strip()',
        "quote = quote.strip()",
    ),
    # extract_dm_text: порог обрезки цитаты расширен на порядок
    (
        "backend/helpers.py",
        "if len(quote) > 80:",
        "if len(quote) > 800:",
    ),
    # extract_dm_text: пустое тело больше не даёт «голую» цитату
    (
        "backend/helpers.py",
        'return f"↪ {quote}\\n\\n{body}" if body else f"↪ {quote}"',
        'return f"↪ {quote}\\n\\n{body}"',
    ),
    # normalize_username: http:// перестаёт распознаваться
    (
        "backend/helpers.py",
        'for prefix in ("https://", "http://"):',
        'for prefix in ("https://",):',
    ),
    # normalize_username: префикс t.me/ не снимается
    (
        "backend/helpers.py",
        'if s.startswith("t.me/"):\r\n        s = s[len("t.me/"):]',
        'if False:\r\n        s = s[len("t.me/"):]',
    ),
    # normalize_username: хвостовой слэш не срезается
    (
        "backend/helpers.py",
        's = s.lstrip("@").strip().rstrip("/")',
        's = s.lstrip("@").strip()',
    ),
    # normalize_username: при лишнем сегменте пути берётся не тот кусок
    (
        "backend/helpers.py",
        'if "/" in s:\r\n        s = s.split("/", 1)[0]',
        'if "/" in s:\r\n        s = s.split("/", 1)[-1]',
    ),
    # normalize_username: телефоны с «+» больше не отсеиваются
    (
        "backend/helpers.py",
        'if not s or s.startswith("+"):',
        "if not s:",
    ),
    # normalize_username: служебные пути Telegram (joinchat/c/...) не отсеиваются
    (
        "backend/helpers.py",
        "if s.lower() in _TG_RESERVED_PATHS:",
        "if False:",
    ),
    # fetch_telegram_avatar: перепутан приоритет small/big file_id
    (
        "backend/helpers.py",
        'file_id = getattr(photo, "small_file_id", None) or getattr(photo, "big_file_id", None)',
        'file_id = getattr(photo, "big_file_id", None) or getattr(photo, "small_file_id", None)',
    ),
    # resolve_hr_telegram: удалённый аккаунт больше не отсеивается
    (
        "backend/helpers.py",
        'if getattr(user, "is_bot", False) or getattr(user, "is_deleted", False):',
        'if getattr(user, "is_bot", False):',
    ),
]
