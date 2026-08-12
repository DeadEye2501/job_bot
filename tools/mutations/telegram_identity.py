"""Поломки для правил ника `backend/domain/telegram_identity.py`.

Набор отпочковался от `helpers` заходом Д этапа 4 вместе с самим модулем:
гонять поломки надо против проверок своего предмета, а они разъехались по
трём файлам.
"""

# (файл, что заменить, на что заменить) — по одной осмысленной поломке.
MUTATIONS = [
    # typed_username: негодный ник молча становится отсутствием
    (
        "backend/domain/telegram_identity.py",
        "    if handle is None:\r\n"
        '        raise ValueError("ник не похож на телеграмовский")\r\n',
        "",
    ),
    # typed_username: одна собачка перестаёт считаться пустым полем
    (
        "backend/domain/telegram_identity.py",
        '    typed = str(value).strip().lstrip("@").strip()',
        "    typed = str(value).strip()",
    ),
    # typed_username: ник из формы разбирают правилом объявления
    (
        "backend/domain/telegram_identity.py",
        "    handle = normalize_username(typed, typed_by_a_person=True)",
        "    handle = normalize_username(typed)",
    ),
    # normalize_username: поблажка по длине достаётся и разбору объявления
    (
        "backend/domain/telegram_identity.py",
        "    allowed = _TG_TYPED_USERNAME_RE if typed_by_a_person else _TG_USERNAME_RE",
        "    allowed = _TG_TYPED_USERNAME_RE",
    ),
    # normalize_username: http:// перестаёт распознаваться
    (
        "backend/domain/telegram_identity.py",
        'for prefix in ("https://", "http://"):',
        'for prefix in ("https://",):',
    ),
    # normalize_username: хвостовой слэш не срезается
    (
        "backend/domain/telegram_identity.py",
        's = s.lstrip("@").strip().rstrip("/")',
        's = s.lstrip("@").strip()',
    ),
    # normalize_username: при лишнем сегменте пути берётся не тот кусок
    (
        "backend/domain/telegram_identity.py",
        'if "/" in s:\r\n        s = s.split("/", 1)[0]',
        'if "/" in s:\r\n        s = s.split("/", 1)[-1]',
    ),
    # normalize_username: телефоны с «+» больше не отсеиваются
    (
        "backend/domain/telegram_identity.py",
        'if not s or s.startswith("+"):',
        "if not s:",
    ),
    # normalize_username: служебные пути Telegram (joinchat/c/...) не отсеиваются
    (
        "backend/domain/telegram_identity.py",
        "if s.lower() in _TG_RESERVED_PATHS:",
        "if False:",
    ),
]
