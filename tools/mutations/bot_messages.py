"""Поломки для всего, что бот пишет и читает в личных переписках.

Отправка отклика, ручная отправка из «Контактов», отметки о прочтении и
обработчики входящего, правки, удаления и эха собственного сообщения.

Где поломка захватывает конец строки, перевод пишется через `CRLF`: рабочее
дерево здесь с виндовыми переводами, и поиск по `\\n` не находит ничего.
"""

CRLF = "\r\n"

MUTATIONS = [
    # send: HR без адреса перестаёт отбиваться
    (
        "backend/bot/send.py",
        "    if target is None:" + CRLF
        + "        logger.warning(" + CRLF
        + '            "Bot.send: hr %s has no telegram_user_id or username,'     ' skipping (vacancy=%s)",' + CRLF
        + "            hr.id, vacancy_id," + CRLF
        + "        )" + CRLF
        + "        return False" + CRLF,
        "",
    ),
    # send: выключенный режим перестаёт отбивать отправку
    (
        "backend/bot/send.py",
        "    if (await bot._current_mode()) is BotMode.OFF:" + CRLF
        + "        logger.warning(" + CRLF
        + '            "Bot.send: BotMode.OFF, suppressed send to %s (vacancy=%s)",'     + CRLF,
        "    if False:" + CRLF
        + "        logger.warning(" + CRLF
        + '            "Bot.send: BotMode.OFF, suppressed send to %s (vacancy=%s)",'     + CRLF,
    ),
    # send: чёрный список перестаёт отбивать отправку
    (
        "backend/bot/send.py",
        "    if bl_value:" + CRLF
        + "        logger.warning(" + CRLF
        + '            "Bot.send: hr %s in blacklist (%s), suppressed (vacancy=%s)",'     + CRLF,
        "    if False:" + CRLF
        + "        logger.warning(" + CRLF
        + '            "Bot.send: hr %s in blacklist (%s), suppressed (vacancy=%s)",'     + CRLF,
    ),
    # send: тестовый режим перестаёт заглушать отправку
    (
        "backend/bot/send.py",
        "    suppressed = bot._dry_run or telegram.SEND_LOCKED",
        "    suppressed = telegram.SEND_LOCKED",
    ),
    # send: заглушенная отправка всё равно пишет сообщение в переписку
    (
        "backend/bot/send.py",
        "        if not outcome.suppressed:" + CRLF + "            session.add(",
        "        if True:" + CRLF + "            session.add(",
    ),
    # send: срок запрета не запоминается
    (
        "backend/bot/send.py",
        '        await bot._rs.set_app("flood_wait_until_ts", str(_time.time() + secs))',
        '        await bot._rs.set_app("flood_wait_until_ts", "0")',
    ),
    # send: удачная отправка запомненный запрет не снимает
    (
        "backend/bot/send.py",
        "    if bot._rs.flood_wait_until_ts <= 0:" + CRLF + "        return" + CRLF,
        "    if True:" + CRLF + "        return" + CRLF,
    ),
    # send: ручная отправка перестаёт отличаться от авто
    (
        "backend/bot/send.py",
        '    return "Ручная отправка." if force else "Авто-отправка отклика."',
        '    return "Ручная отправка." if not force '
        'else "Авто-отправка отклика."',
    ),
    # send: признак ручной отправки не доходит до охраны статуса
    (
        "backend/repository/vacancies_life.py",
        "    if vacancy is None or not should_apply_status(" + CRLF
        + "        vacancy.status, VacancyStatus.APPLIED, force=force" + CRLF,
        "    if vacancy is None or not should_apply_status(" + CRLF
        + "        vacancy.status, VacancyStatus.APPLIED, force=False" + CRLF,
    ),
    # send: запасная перестановка статуса пропадает
    (
        "backend/bot/send.py",
        "            if await mark_vacancy_applied(" + CRLF,
        "            if False and await mark_vacancy_applied(" + CRLF,
    ),
    # send: отметка о заглушенной отправке врёт
    (
        "backend/bot/send.py",
        '                        "suppressed": suppressed,',
        '                        "suppressed": False,',
    ),
    # mark_hr_chat_read: выключенный бот всё равно гасит непрочитанное
    (
        "backend/bot/chat.py",
        "    if (await bot._current_mode()) is BotMode.OFF:" + CRLF
        + "        return 0" + CRLF,
        "",
    ),
    # _move_status: перевод статуса остаётся в истории без подписи
    (
        "backend/repository/vacancies_life.py",
        "        explanation=_ensure_trailing_period(explanation)," + CRLF,
        "        explanation=None," + CRLF,
    ),
    # mark_incoming_read: отметка ставится и на исходящие
    (
        "backend/repository/messages.py",
        "            Message.hr_id == hr_id," + CRLF
        + "            Message.is_incoming," + CRLF
        + "            Message.read_at.is_(None)," + CRLF,
        "            Message.hr_id == hr_id," + CRLF
        + "            Message.read_at.is_(None)," + CRLF,
    ),
    # mark_incoming_read: отметка ставится всем HR разом
    (
        "backend/repository/messages.py",
        "            Message.hr_id == hr_id," + CRLF
        + "            Message.is_incoming," + CRLF,
        "            Message.is_incoming," + CRLF,
    ),
    # mark_incoming_read: надгробия непрочитанного не гасятся
    (
        "backend/repository/messages.py",
        "            Message.hr_id == hr_id," + CRLF
        + "            Message.is_incoming," + CRLF
        + "            Message.read_at.is_(None)," + CRLF,
        "            Message.hr_id == hr_id," + CRLF
        + "            *UNREAD_INCOMING," + CRLF,
    ),
    # mark_incoming_read: уже прочитанное помечается заново
    (
        "backend/repository/messages.py",
        "            Message.hr_id == hr_id," + CRLF
        + "            Message.is_incoming," + CRLF
        + "            Message.read_at.is_(None)," + CRLF,
        "            Message.hr_id == hr_id," + CRLF
        + "            Message.is_incoming," + CRLF,
    ),
    # mark_hr_chat_read: Telegram беспокоят и когда гасить нечего
    (
        "backend/bot/chat.py",
        "    if updated > 0 and target is not None:",
        "    if target is not None:",
    ),
    # persist_outgoing_dm: повтор считается новой записью и будит окно
    (
        "backend/flows/dm.py",
        "            if not saved:" + CRLF,
        "            if False:" + CRLF,
    ),
    # persist_outgoing_dm: заслон снят, и вложение качают поверх кэша.
    # Строки не стираются, а обессмысливаются условием: снос оставил бы
    # `async with` без тела, а несобираемый файл инструмент засчитал бы
    # пойманным, не дойдя до проверок.
    (
        "backend/flows/dm.py",
        "        if await find_outgoing_message(session, hr_id, msg.id) is not None:" + CRLF,
        "        if False:" + CRLF,
    ),
    # save_outgoing_message: после конфликта сессия не откатывается
    (
        "backend/repository/messages.py",
        "        await session.rollback()" + CRLF,
        "",
    ),
    # _on_dm_outgoing: эхо своей же отправки перестаёт будить окно
    (
        "backend/bot/updates.py",
        '    if outcome == "not_stored":' + CRLF,
        '    if outcome != "stored":' + CRLF,
    ),
    # on_raw_update: чужой род оповещения перестаёт отсеиваться
    (
        "backend/bot/updates.py",
        "    if not isinstance(update, _UpdateReadHistoryOutbox):" + CRLF
        + "        return" + CRLF,
        "",
    ),
    # on_raw_update: групповые чаты перестают отсеиваться
    (
        "backend/bot/updates.py",
        "    if not isinstance(peer, _PeerUser):" + CRLF + "        return" + CRLF,
        "",
    ),
    # on_raw_update: отметка заходит дальше названного сообщения
    (
        "backend/bot/updates.py",
        "                Message.tg_message_id <= max_id,",
        "                Message.tg_message_id >= max_id,",
    ),
    # on_raw_update: окно дёргают и когда ничего не изменилось
    (
        "backend/bot/updates.py",
        "    if updated:" + CRLF
        + '        fire(bot.on_hr_read, "on_hr_read", hr_id, max_id)' + CRLF,
        '    fire(bot.on_hr_read, "on_hr_read", hr_id, max_id)' + CRLF,
    ),
    # send_to_hr_chat: пустое сообщение перестаёт отбиваться
    (
        "backend/bot/chat.py",
        "    if not clean:" + CRLF
        + '        raise RuntimeError("Пустое сообщение.")' + CRLF,
        "",
    ),
    # send_to_hr_chat: пробелы по краям перестают обрезаться
    (
        "backend/bot/chat.py",
        '    clean = (text or "").strip()',
        '    clean = text or ""',
    ),
    # on_dm_edit: пометка «изменено» не ставится
    (
        "backend/bot/updates.py",
        "            .values(text=extract_dm_text(msg), is_edited=True)",
        "            .values(text=extract_dm_text(msg))",
    ),
    # on_dm_edit: направление сообщения перестаёт учитываться
    (
        "backend/bot/updates.py",
        "                Message.tg_message_id == msg.id," + CRLF
        + "                Message.is_incoming.is_(is_incoming)," + CRLF,
        "                Message.tg_message_id == msg.id," + CRLF,
    ),
    # on_dm_edit: признак «своё» перестаёт влиять на направление
    (
        "backend/bot/updates.py",
        '    is_incoming = bool(getattr(msg, "from_user", None)' + CRLF
        + '                       and not getattr(msg, "outgoing", False))' + CRLF,
        '    is_incoming = bool(getattr(msg, "from_user", None))' + CRLF,
    ),
    # on_dm_edit: отправитель перестаёт влиять на направление
    (
        "backend/bot/updates.py",
        '    is_incoming = bool(getattr(msg, "from_user", None)' + CRLF
        + '                       and not getattr(msg, "outgoing", False))' + CRLF,
        '    is_incoming = not getattr(msg, "outgoing", False)' + CRLF,
    ),
    # on_dm_edit: имя переписки перестаёт участвовать в опознании HR
    (
        "backend/bot/updates.py",
        '    chat_username = getattr(msg.chat, "username", None)' + CRLF,
        "    chat_username = None" + CRLF,
    ),
    # on_dm_edit: своя правка тоже правит текст, ждущий разбора
    (
        "backend/bot/updates.py",
        "    if updated and is_incoming:",
        "    if updated:",
    ),
    # on_dm_delete: строка выбрасывается вместо пометки
    (
        "backend/bot/updates.py",
        "            .values(is_deleted=True)",
        "            .values(is_deleted=False)",
    ),
    # on_dm_delete: непрочитанное надгробие продолжает числиться
    (
        "backend/bot/updates.py",
        "            .where(*where_clauses, Message.is_incoming,"     " Message.read_at.is_(None))" + CRLF
        + "            .values(read_at=now)" + CRLF,
        "            .where(*where_clauses, Message.is_incoming,"     " Message.read_at.is_(None))" + CRLF
        + "            .values()" + CRLF,
    ),
    # on_dm_delete: безымянная уборка задевает и исходящие
    (
        "backend/bot/updates.py",
        "                    Message.tg_message_id.in_(chatless_ids)," + CRLF
        + "                    Message.is_incoming," + CRLF
        + "                ]," + CRLF,
        "                    Message.tg_message_id.in_(chatless_ids)," + CRLF
        + "                ]," + CRLF,
    ),
    # on_dm_delete: имя переписки перестаёт участвовать в опознании HR
    (
        "backend/bot/updates.py",
        '            return getattr(chat, "username", None)' + CRLF,
        "            return None" + CRLF,
    ),
    # persist_outgoing_dm: эхо своей отправки пишется второй строкой
    (
        "backend/flows/dm.py",
        '            return "already_stored"' + CRLF,
        '            pass' + CRLF,
    ),
    # on_dm_outgoing: выключенный бот всё равно подхватывает написанное
    (
        "backend/bot/updates.py",
        "    if (await bot._current_mode()) is BotMode.OFF:" + CRLF
        + "        return" + CRLF
        + "    if not msg.chat:" + CRLF
        + "        return" + CRLF
        + CRLF
        + "    recipient_id = msg.chat.id",
        "    if not msg.chat:" + CRLF
        + "        return" + CRLF
        + CRLF
        + "    recipient_id = msg.chat.id",
    ),
    # on_dm_outgoing: имя получателя перестаёт участвовать в опознании HR
    (
        "backend/bot/updates.py",
        '    recipient_username = getattr(msg.chat, "username", None)',
        "    recipient_username = None",
    ),
    # on_dm: выключенный бот всё равно разбирает входящее
    (
        "backend/bot/updates.py",
        "    # Off mode silences everything, including reading HR replies." + CRLF
        + "    if (await bot._current_mode()) is BotMode.OFF:" + CRLF
        + "        return" + CRLF,
        "",
    ),
    # on_dm: имя отправителя перестаёт участвовать в опознании HR
    (
        "backend/bot/updates.py",
        "                msg.from_user.id," + CRLF
        + "                msg.from_user.username," + CRLF,
        "                msg.from_user.id," + CRLF
        + "                None," + CRLF,
    ),
    # telegram_peer: ник предпочитается учётной записи — письмо уйдёт
    # чужому человеку, если ник сменили. Ломается чужой файл нарочно:
    # строка живёт в `usernames`, а убивают её проверки этого набора.
    (
        "backend/domain/telegram_identity.py",
        "    return hr.telegram_user_id or hr.telegram_username",
        "    return hr.telegram_username or hr.telegram_user_id",
    ),
]
