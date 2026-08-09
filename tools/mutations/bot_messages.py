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
    # send: адрес выбирается именем, а не номером
    (
        "backend/bot/send.py",
        "    target = hr.telegram_user_id or hr.telegram_username" + CRLF
        + "    if target is None:" + CRLF
        + "        logger.warning(",
        "    target = hr.telegram_username or hr.telegram_user_id" + CRLF
        + "    if target is None:" + CRLF
        + "        logger.warning(",
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
        "            if not suppressed:" + CRLF + "                session.add(",
        "            if True:" + CRLF + "                session.add(",
    ),
    # send: срок запрета не запоминается
    (
        "backend/bot/send.py",
        '                    "flood_wait_until_ts", str(until)',
        '                    "flood_wait_until_ts", "0"',
    ),
    # send: удачная отправка запомненный запрет не снимает
    (
        "backend/bot/send.py",
        "    if not suppressed and bot._rs.flood_wait_until_ts > 0:",
        "    if False:",
    ),
    # send: ручная отправка перестаёт отличаться от авто
    (
        "backend/bot/send.py",
        "                    kind_label = (" + CRLF
        + '                        "Ручная отправка."' + CRLF
        + "                        if force" + CRLF,
        "                    kind_label = (" + CRLF
        + '                        "Ручная отправка."' + CRLF
        + "                        if not force" + CRLF,
    ),
    # send: признак ручной отправки не доходит до охраны статуса
    (
        "backend/bot/send.py",
        "                if v is not None and should_apply_status(" + CRLF
        + "                    v.status, VacancyStatus.APPLIED, force=force" + CRLF
        + "                ):" + CRLF
        + "                    previous_status = v.status",
        "                if v is not None and should_apply_status(" + CRLF
        + "                    v.status, VacancyStatus.APPLIED, force=False" + CRLF
        + "                ):" + CRLF
        + "                    previous_status = v.status",
    ),
    # send: запасная перестановка статуса пропадает
    (
        "backend/bot/send.py",
        "                        v.status = VacancyStatus.APPLIED" + CRLF
        + "                        await session.commit()" + CRLF,
        "                        pass" + CRLF,
    ),
    # send: отметка о заглушенной отправке врёт
    (
        "backend/bot/send.py",
        '                            "suppressed": suppressed,',
        '                            "suppressed": False,',
    ),
    # mark_hr_chat_read: выключенный бот всё равно гасит непрочитанное
    (
        "backend/bot/chat.py",
        "    if (await bot._current_mode()) is BotMode.OFF:" + CRLF
        + "        return 0" + CRLF,
        "",
    ),
    # mark_hr_chat_read: отметка ставится и на исходящие
    (
        "backend/bot/chat.py",
        "                Message.hr_id == hr_id," + CRLF
        + "                Message.is_incoming," + CRLF
        + "                Message.read_at.is_(None)," + CRLF,
        "                Message.hr_id == hr_id," + CRLF
        + "                Message.read_at.is_(None)," + CRLF,
    ),
    # mark_hr_chat_read: уже прочитанное помечается заново
    (
        "backend/bot/chat.py",
        "                Message.hr_id == hr_id," + CRLF
        + "                Message.is_incoming," + CRLF
        + "                Message.read_at.is_(None)," + CRLF,
        "                Message.hr_id == hr_id," + CRLF
        + "                Message.is_incoming," + CRLF,
    ),
    # mark_hr_chat_read: Telegram беспокоят и когда гасить нечего
    (
        "backend/bot/chat.py",
        "    if updated > 0 and target is not None:",
        "    if target is not None:",
    ),
    # mark_hr_chat_read: адрес выбирается именем, а не номером
    (
        "backend/bot/chat.py",
        "        target = hr.telegram_user_id or hr.telegram_username" + CRLF
        + "        res = await session.execute(",
        "        target = hr.telegram_username or hr.telegram_user_id" + CRLF
        + "        res = await session.execute(",
    ),
    # _on_dm_outgoing: номер снова читается у HR после сорвавшейся вставки
    (
        "backend/bot/updates.py",
        '                "Outgoing DM dedup: hr=%d tg_msg=%d already saved",' + CRLF
        + "                hr_id, msg.id,",
        '                "Outgoing DM dedup: hr=%d tg_msg=%d already saved",' + CRLF
        + "                hr.id, msg.id,",
    ),
    # _on_dm_outgoing: номер снова читается у HR в общей ветке разбора
    (
        "backend/bot/updates.py",
        '                extra={"hr_id": hr_id, "tg_message_id": msg.id},',
        '                extra={"hr_id": hr.id, "tg_message_id": msg.id},',
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
        "    if updated and bot.on_hr_read is not None:",
        "    if bot.on_hr_read is not None:",
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
        '                    chat_username = getattr(chat, "username", None)' + CRLF,
        "                    chat_username = None" + CRLF,
    ),
    # on_dm_outgoing: эхо своей отправки пишется второй строкой
    (
        "backend/bot/updates.py",
        "        if existing is not None:" + CRLF
        + "            # Echo собственного Bot.send-а",
        "        if False:" + CRLF + "            # Echo собственного Bot.send-а",
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
]
