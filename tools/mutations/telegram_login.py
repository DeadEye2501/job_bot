"""Поломки для `backend/telegram_login.py`.

Вход по коду руками не проверить — нужен настоящий номер и код из Telegram, —
поэтому все семнадцать его сторожей писались против подделки клиента и ни разу
не краснели по-настоящему. Этот набор и есть их проверка: ломается то, что
легко испортить случайно при следующей правке входа.

Ломаем условием и подменой значения, а не сносом строк: несобираемый файл
`tools/mutate.py` засчитал бы пойманным, не дойдя до проверок.

Где поломка захватывает конец строки, перевод пишется через `CRLF`: рабочее
дерево здесь с виндовыми переводами, и поиск по `\\n` не находит ничего.
"""

CRLF = "\r\n"

MUTATIONS = [
    # send_code: клиент собирается с файлом сессии на диске
    (
        "backend/telegram_login.py",
        "            in_memory=True," + CRLF,
        "            in_memory=False," + CRLF,
    ),
    # send_code: имя сессии у обоих входов становится общим
    (
        "backend/telegram_login.py",
        "            name=self._session_name," + CRLF,
        '            name="job_bot",' + CRLF,
    ),
    # send_code: отпечаток кода не запоминается
    (
        "backend/telegram_login.py",
        "            self._phone_code_hash = sent.phone_code_hash" + CRLF,
        "            self._phone_code_hash = None" + CRLF,
    ),
    # send_code: прежняя попытка не закрывается перед новой
    (
        "backend/telegram_login.py",
        "        await self.forget()" + CRLF,
        "        pass" + CRLF,
    ),
    # send_code: срок без числа снова показывается нулём секунд
    (
        "backend/telegram_login.py",
        '    waiting = _humanize_duration(secs) if secs else "некоторое время"',
        "    waiting = _humanize_duration(secs)",
    ),
    # confirm_code: код уходит в Telegram без отпечатка своей отправки
    (
        "backend/telegram_login.py",
        "                phone_code_hash=self._phone_code_hash," + CRLF,
        "                phone_code_hash=None," + CRLF,
    ),
    # confirm_password: набранный пароль не доезжает до настроек
    (
        "backend/telegram_login.py",
        '        self._creds["password"] = password' + CRLF,
        "        pass" + CRLF,
    ),
    # _save: ник спрашивают и тогда, когда его никто не ждёт
    (
        "backend/telegram_login.py",
        "            if self._on_saved is not None:" + CRLF,
        "            if True:" + CRLF,
    ),
    # _save: сессия сохраняется под чужим номером
    (
        "backend/telegram_login.py",
        '            phone=creds["phone"],' + CRLF,
        '            phone="",' + CRLF,
    ),
    # _save: попытка не забывается после сохранения
    (
        "backend/telegram_login.py",
        "        self._drop()" + CRLF + "        logger.info(",
        "        logger.info(",
    ),
    # forget: сокет остаётся открытым
    (
        "backend/telegram_login.py",
        "        await _safe_disconnect(old)" + CRLF,
        "        pass" + CRLF,
    ),
]
