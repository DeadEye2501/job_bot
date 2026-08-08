"""Поломки для вложений в `backend/bot.py`: способ отправки, пути, скачивание.

Где поломка захватывает конец строки, перевод пишется через `CRLF`: рабочее
дерево здесь с виндовыми переводами, и поиск по `\\n` не находит ничего.
"""

CRLF = "\r\n"

MUTATIONS = [
    # _looks_like_photo: непринимаемое расширение перестаёт отсеиваться
    (
        "backend/bot/client.py",
        "    if suffix not in PHOTO_EXTS:" + CRLF + "        return False" + CRLF,
        "",
    ),
    # _looks_like_photo: регистр расширения перестаёт опускаться
    (
        "backend/bot/client.py",
        "    suffix = path.suffix.lower()",
        "    suffix = path.suffix",
    ),
    # _looks_like_photo: список принимаемых расширений теряет одно
    (
        "backend/bot/client.py",
        'PHOTO_EXTS = {".png", ".jpg", ".jpeg", ".webp"}',
        'PHOTO_EXTS = {".png", ".jpg", ".jpeg"}',
    ),
    # _media_cache_path: номер собеседника выпадает из пути
    (
        "backend/bot/client.py",
        '    return MEDIA_DIR / str(hr_id) / f"{tg_message_id}{ext}"',
        '    return MEDIA_DIR / f"{tg_message_id}{ext}"',
    ),
    # _media_path_for_db: путь пишется целиком, а не относительно папки
    (
        "backend/bot/client.py",
        "        return p.relative_to(MEDIA_DIR.resolve()).as_posix()",
        "        return p.as_posix()",
    ),
    # _download_media: картинка получает расширение документа
    (
        "backend/bot/client.py",
        '        ext = ".jpg"  # Pyrogram delivers photos as JPEGs',
        '        ext = ".bin"',
    ),
    # _download_media: уже скачанный файл качается заново
    (
        "backend/bot/client.py",
        "    if out.exists():" + CRLF + "        return _media_path_for_db(out)" + CRLF,
        "",
    ),
    # _download_media: сбой скачивания перестаёт быть отсутствием
    (
        "backend/bot/client.py",
        "    if not path:" + CRLF + "        return None" + CRLF,
        "",
    ),
    # _shares_provider: ключ перестаёт сравниваться
    (
        "backend/bot/client.py",
        "        and a.base_url == b.base_url" + CRLF
        + "        and a.api_key == b.api_key" + CRLF,
        "        and a.base_url == b.base_url" + CRLF,
    ),
    # _shares_provider: сравнивается ещё и модель
    (
        "backend/bot/client.py",
        "        and a.api_key == b.api_key" + CRLF,
        "        and a.api_key == b.api_key" + CRLF
        + "        and a.model == b.model" + CRLF,
    ),
    # _shares_provider: отсутствие настройки перестаёт разводить клиентов
    (
        "backend/bot/client.py",
        "        a is not None" + CRLF + "        and b is not None" + CRLF,
        "",
    ),
    # send_to_hr_media: картинка уходит документом
    (
        "backend/bot/client.py",
        "        if as_photo:" + CRLF
        + "            pyro_msg = await self._client.send_photo(target, str(src))" + CRLF
        + "        else:" + CRLF
        + "            pyro_msg = await self._client.send_document(target, str(src))" + CRLF,
        "        pyro_msg = await self._client.send_document(target, str(src))" + CRLF,
    ),
    # send_to_hr_media: предел размера перестаёт зависеть от вида файла
    (
        "backend/bot/client.py",
        "        cap = PHOTO_SIZE_LIMIT if as_photo else DOCUMENT_SIZE_LIMIT",
        "        cap = DOCUMENT_SIZE_LIMIT",
    ),
    # send_to_hr_media: предел становится исключающим
    (
        "backend/bot/client.py",
        "        if size > cap:",
        "        if size >= cap:",
    ),
    # send_to_hr_media: имя запоминается и у картинки
    (
        "backend/bot/client.py",
        "        media_name = None if as_photo else src.name",
        "        media_name = src.name",
    ),
    # send_to_hr_media: несуществующий путь перестаёт отбиваться
    (
        "backend/bot/client.py",
        "        if not src.exists() or not src.is_file():" + CRLF
        + '            raise RuntimeError(f"Файл не найден: {file_path}")' + CRLF,
        "",
    ),
]
