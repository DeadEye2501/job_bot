"""Поломки для вложений в `backend/bot/`: способ отправки, пути, скачивание.

Где поломка захватывает конец строки, перевод пишется через `CRLF`: рабочее
дерево здесь с виндовыми переводами, и поиск по `\\n` не находит ничего.
"""

CRLF = "\r\n"

MUTATIONS = [
    # looks_like_photo: непринимаемое расширение перестаёт отсеиваться
    (
        "backend/bot/media.py",
        "    if suffix not in PHOTO_EXTS:" + CRLF + "        return False" + CRLF,
        "",
    ),
    # looks_like_photo: регистр расширения перестаёт опускаться
    (
        "backend/bot/media.py",
        "    suffix = path.suffix.lower()",
        "    suffix = path.suffix",
    ),
    # looks_like_photo: список принимаемых расширений теряет одно
    (
        "backend/bot/media.py",
        'PHOTO_EXTS = {".png", ".jpg", ".jpeg", ".webp"}',
        'PHOTO_EXTS = {".png", ".jpg", ".jpeg"}',
    ),
    # looks_like_photo: содержимое перестаёт проверяться, верят расширению
    (
        "backend/bot/media.py",
        "    return _has_photo_content(path)",
        "    return True",
    ),
    # _has_photo_content: подпись WEBP перестаёт узнаваться
    (
        "backend/bot/media.py",
        '    return head[:4] == b"RIFF" and head[8:12] == b"WEBP"',
        "    return False",
    ),
    # _has_photo_content: нечитаемый файл уходит картинкой
    (
        "backend/bot/media.py",
        '        logger.warning("не удалось прочесть начало файла %s", path)' + CRLF
        + "        return False",
        '        logger.warning("не удалось прочесть начало файла %s", path)' + CRLF
        + "        return True",
    ),
    # media_cache_path: номер собеседника выпадает из пути
    (
        "backend/bot/media.py",
        '    return MEDIA_DIR / str(hr_id) / f"{tg_message_id}{ext}"',
        '    return MEDIA_DIR / f"{tg_message_id}{ext}"',
    ),
    # media_path_for_db: путь пишется целиком, а не относительно папки
    (
        "backend/bot/media.py",
        "        return p.relative_to(MEDIA_DIR.resolve()).as_posix()",
        "        return p.as_posix()",
    ),
    # _cache_ext: картинка получает расширение документа
    (
        "backend/bot/media.py",
        '        return ".jpg"',
        '        return ".bin"',
    ),
    # download_media: уже скачанный файл качается заново
    (
        "backend/bot/media.py",
        "    if out.exists():" + CRLF + "        return media_path_for_db(out)" + CRLF,
        "",
    ),
    # download_media: место для файла готовится мимо разбора ошибок
    (
        "backend/bot/media.py",
        "    try:" + CRLF
        + "        out.parent.mkdir(parents=True, exist_ok=True)" + CRLF,
        "    out.parent.mkdir(parents=True, exist_ok=True)" + CRLF
        + "    try:" + CRLF,
    ),
    # download_media: сбой скачивания перестаёт быть отсутствием
    (
        "backend/bot/media.py",
        "    if not path:" + CRLF + "        return None" + CRLF,
        "",
    ),
    # _shares_provider: ключ перестаёт сравниваться
    (
        "backend/bot/send.py",
        "        and a.base_url == b.base_url" + CRLF
        + "        and a.api_key == b.api_key" + CRLF,
        "        and a.base_url == b.base_url" + CRLF,
    ),
    # _shares_provider: сравнивается ещё и модель
    (
        "backend/bot/send.py",
        "    and a.api_key == b.api_key" + CRLF,
        "    and a.api_key == b.api_key" + CRLF
        + "    and a.model == b.model" + CRLF,
    ),
    # _shares_provider: отсутствие настройки перестаёт разводить клиентов
    (
        "backend/bot/send.py",
        "        a is not None" + CRLF + "        and b is not None" + CRLF,
        "",
    ),
    # send_to_hr_media: картинка уходит документом
    (
        "backend/bot/chat.py",
        "    if as_photo:" + CRLF
        + "        pyro_msg = await bot._client.send_photo(target, str(src))" + CRLF
        + "    else:" + CRLF
        + "        pyro_msg = await bot._client.send_document(target, str(src))" + CRLF,
        "    pyro_msg = await bot._client.send_document(target, str(src))" + CRLF,
    ),
    # send_to_hr_media: предел размера перестаёт зависеть от вида файла
    (
        "backend/bot/chat.py",
        "    cap = media.PHOTO_SIZE_LIMIT if as_photo else media.DOCUMENT_SIZE_LIMIT",
        "    cap = media.DOCUMENT_SIZE_LIMIT",
    ),
    # send_to_hr_media: предел становится исключающим
    (
        "backend/bot/chat.py",
        "    if size > cap:",
        "    if size >= cap:",
    ),
    # send_to_hr_media: имя запоминается и у картинки
    (
        "backend/bot/chat.py",
        "            media_name=None if as_photo else src.name,",
        "            media_name=src.name,",
    ),
    # cache_sent_file: место для копии готовится мимо разбора ошибок
    (
        "backend/bot/media.py",
        "    try:" + CRLF
        + "        dest.parent.mkdir(parents=True, exist_ok=True)" + CRLF,
        "    dest.parent.mkdir(parents=True, exist_ok=True)" + CRLF
        + "    try:" + CRLF,
    ),
    # send_to_hr_media: несуществующий путь перестаёт отбиваться
    (
        "backend/bot/chat.py",
        "    if not src.exists() or not src.is_file():" + CRLF
        + '        raise RuntimeError(f"Файл не найден: {file_path}")' + CRLF,
        "",
    ),
]
