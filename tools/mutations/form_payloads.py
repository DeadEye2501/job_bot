"""Поломки для чтения нагрузок форм окна — `client/form_payloads.py`.

Имена ключей здесь — подпись чужого вызова: слоты зовут заведение записи
развёрткой словаря, и переименованный ключ роняет форму у пользователя,
ничего не записав. Отсюда цели на сами ключи, а не только на правила.

Где поломка захватывает конец строки, перевод берётся из `CRLF`. В хранилище
этот файл лежит с переводами в один знак, а в рабочем дереве — в два: их
ставит сам git при выгрузке, и набор читает именно дерево.
"""

CRLF = "\r\n"

MUTATIONS = [
    # read_new_hr_fields: ник не разбирается и едет в колонку как введён
    (
        "client/form_payloads.py",
        "    username = None if typed is None else typed_username(typed)",
        "    username = typed",
    ),
    # read_new_hr_fields: ключ ника разошёлся с подписью заведения
    (
        "client/form_payloads.py",
        '        "telegram_username": username,',
        '        "telegram_handle": username,',
    ),
    # read_new_hr_fields: номер учётной записи уезжает строкой
    (
        "client/form_payloads.py",
        '"telegram_user_id": None if raw_user_id in (None, "") else int(raw_user_id),',
        '"telegram_user_id": None if raw_user_id in (None, "") else raw_user_id,',
    ),
    # read_new_company_fields: ключ сайта разошёлся с подписью заведения
    (
        "client/form_payloads.py",
        '        "website": none_if_empty(payload.get("website")),',
        '        "site": none_if_empty(payload.get("website")),',
    ),
    # read_company_spellings: написания списком перестают читаться
    (
        "client/form_payloads.py",
        "    elif not isinstance(raw, list):" + CRLF
        + "        raw = []" + CRLF,
        "    else:" + CRLF + "        raw = []" + CRLF,
    ),
    # read_company_spellings: пустое написание попадает в перечень
    (
        "client/form_payloads.py",
        "        spelling for spelling in (str(a).strip() for a in raw) if spelling",
        "        spelling for spelling in (str(a).strip() for a in raw)",
    ),
    # hr_is_identified: заметки сходят за способ назвать человека
    (
        "client/form_payloads.py",
        '        for key in ("name", "telegram_username", "telegram_user_id")',
        '        for key in ("name", "telegram_username", "telegram_user_id", "notes")',
    ),
    # none_if_empty: пробельная строка перестаёт считаться отсутствием
    (
        "client/form_payloads.py",
        "    text = str(value).strip()" + CRLF,
        "    text = str(value)" + CRLF,
    ),
]
