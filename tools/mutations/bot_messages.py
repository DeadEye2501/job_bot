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
        "backend/bot.py",
        "        if target is None:" + CRLF
        + "            logger.warning(" + CRLF
        + '                "Bot.send: hr %s has no telegram_user_id or username,'
        ' skipping (vacancy=%s)",' + CRLF
        + "                hr.id, vacancy_id," + CRLF
        + "            )" + CRLF
        + "            return False" + CRLF,
        "",
    ),
    # send: выключенный режим перестаёт отбивать отправку
    (
        "backend/bot.py",
        "        if (await self._current_mode()) is BotMode.OFF:" + CRLF
        + "            logger.warning(" + CRLF
        + '                "Bot.send: BotMode.OFF, suppressed send to %s (vacancy=%s)",'
        + CRLF,
        "        if False:" + CRLF
        + "            logger.warning(" + CRLF
        + '                "Bot.send: BotMode.OFF, suppressed send to %s (vacancy=%s)",'
        + CRLF,
    ),
    # send: чёрный список перестаёт отбивать отправку
    (
        "backend/bot.py",
        "        if bl_value:" + CRLF
        + "            logger.warning(" + CRLF
        + '                "Bot.send: hr %s in blacklist (%s), suppressed (vacancy=%s)",'
        + CRLF,
        "        if False:" + CRLF
        + "            logger.warning(" + CRLF
        + '                "Bot.send: hr %s in blacklist (%s), suppressed (vacancy=%s)",'
        + CRLF,
    ),
    # send: адрес выбирается именем, а не номером
    (
        "backend/bot.py",
        "        target = hr.telegram_user_id or hr.telegram_username" + CRLF
        + "        if target is None:" + CRLF
        + "            logger.warning(",
        "        target = hr.telegram_username or hr.telegram_user_id" + CRLF
        + "        if target is None:" + CRLF
        + "            logger.warning(",
    ),
    # send: тестовый режим перестаёт заглушать отправку
    (
        "backend/bot.py",
        "        suppressed = self._dry_run or telegram.SEND_LOCKED",
        "        suppressed = telegram.SEND_LOCKED",
    ),
    # send: заглушенная отправка всё равно пишет сообщение в переписку
    (
        "backend/bot.py",
        "                if not suppressed:" + CRLF + "                    session.add(",
        "                if True:" + CRLF + "                    session.add(",
    ),
    # send: срок запрета не запоминается
    (
        "backend/bot.py",
        '                        "flood_wait_until_ts", str(until)',
        '                        "flood_wait_until_ts", "0"',
    ),
    # send: удачная отправка запомненный запрет не снимает
    (
        "backend/bot.py",
        "        if not suppressed and self._rs.flood_wait_until_ts > 0:",
        "        if False:",
    ),
    # send: ручная отправка перестаёт отличаться от авто
    (
        "backend/bot.py",
        "                        kind_label = (" + CRLF
        + '                            "Ручная отправка."' + CRLF
        + "                            if force" + CRLF,
        "                        kind_label = (" + CRLF
        + '                            "Ручная отправка."' + CRLF
        + "                            if not force" + CRLF,
    ),
    # send: признак ручной отправки не доходит до охраны статуса
    (
        "backend/bot.py",
        "                    if v is not None and should_apply_status(" + CRLF
        + "                        v.status, VacancyStatus.APPLIED, force=force" + CRLF
        + "                    ):" + CRLF
        + "                        previous_status = v.status",
        "                    if v is not None and should_apply_status(" + CRLF
        + "                        v.status, VacancyStatus.APPLIED, force=False" + CRLF
        + "                    ):" + CRLF
        + "                        previous_status = v.status",
    ),
    # send: запасная перестановка статуса пропадает
    (
        "backend/bot.py",
        "                            v.status = VacancyStatus.APPLIED" + CRLF
        + "                            await session.commit()" + CRLF,
        "                            pass" + CRLF,
    ),
    # send: отметка о заглушенной отправке врёт
    (
        "backend/bot.py",
        '                                "suppressed": suppressed,',
        '                                "suppressed": False,',
    ),
    # mark_hr_chat_read: выключенный бот всё равно гасит непрочитанное
    (
        "backend/bot.py",
        "        if (await self._current_mode()) is BotMode.OFF:" + CRLF
        + "            return 0" + CRLF,
        "",
    ),
    # mark_hr_chat_read: отметка ставится и на исходящие
    (
        "backend/bot.py",
        "                    Message.hr_id == hr_id," + CRLF
        + "                    Message.is_incoming," + CRLF
        + "                    Message.read_at.is_(None)," + CRLF,
        "                    Message.hr_id == hr_id," + CRLF
        + "                    Message.read_at.is_(None)," + CRLF,
    ),
    # mark_hr_chat_read: уже прочитанное помечается заново
    (
        "backend/bot.py",
        "                    Message.hr_id == hr_id," + CRLF
        + "                    Message.is_incoming," + CRLF
        + "                    Message.read_at.is_(None)," + CRLF,
        "                    Message.hr_id == hr_id," + CRLF
        + "                    Message.is_incoming," + CRLF,
    ),
    # mark_hr_chat_read: Telegram беспокоят и когда гасить нечего
    (
        "backend/bot.py",
        "        if updated > 0 and target is not None:",
        "        if target is not None:",
    ),
    # mark_hr_chat_read: адрес выбирается именем, а не номером
    (
        "backend/bot.py",
        "            target = hr.telegram_user_id or hr.telegram_username" + CRLF
        + "            res = await session.execute(",
        "            target = hr.telegram_username or hr.telegram_user_id" + CRLF
        + "            res = await session.execute(",
    ),
    # _on_raw_update: чужой род оповещения перестаёт отсеиваться
    (
        "backend/bot.py",
        "        if not isinstance(update, _UpdateReadHistoryOutbox):" + CRLF
        + "            return" + CRLF,
        "",
    ),
    # _on_raw_update: групповые чаты перестают отсеиваться
    (
        "backend/bot.py",
        "        if not isinstance(peer, _PeerUser):" + CRLF + "            return" + CRLF,
        "",
    ),
    # _on_raw_update: отметка заходит дальше названного сообщения
    (
        "backend/bot.py",
        "                    Message.tg_message_id <= max_id,",
        "                    Message.tg_message_id >= max_id,",
    ),
    # _on_raw_update: окно дёргают и когда ничего не изменилось
    (
        "backend/bot.py",
        "        if updated and self.on_hr_read is not None:",
        "        if self.on_hr_read is not None:",
    ),
    # send_to_hr_chat: пустое сообщение перестаёт отбиваться
    (
        "backend/bot.py",
        "        if not clean:" + CRLF
        + '            raise RuntimeError("Пустое сообщение.")' + CRLF,
        "",
    ),
    # send_to_hr_chat: пробелы по краям перестают обрезаться
    (
        "backend/bot.py",
        '        clean = (text or "").strip()',
        '        clean = text or ""',
    ),
    # _on_dm_edit: пометка «изменено» не ставится
    (
        "backend/bot.py",
        "                .values(text=extract_dm_text(msg), is_edited=True)",
        "                .values(text=extract_dm_text(msg))",
    ),
    # _on_dm_edit: направление сообщения перестаёт учитываться
    (
        "backend/bot.py",
        "                    Message.tg_message_id == msg.id," + CRLF
        + "                    Message.is_incoming.is_(is_incoming)," + CRLF,
        "                    Message.tg_message_id == msg.id," + CRLF,
    ),
    # _on_dm_edit: признак «своё» перестаёт влиять на направление
    (
        "backend/bot.py",
        '        is_incoming = bool(getattr(msg, "from_user", None)' + CRLF
        + '                           and not getattr(msg, "outgoing", False))' + CRLF,
        '        is_incoming = bool(getattr(msg, "from_user", None))' + CRLF,
    ),
    # _on_dm_edit: отправитель перестаёт влиять на направление
    (
        "backend/bot.py",
        '        is_incoming = bool(getattr(msg, "from_user", None)' + CRLF
        + '                           and not getattr(msg, "outgoing", False))' + CRLF,
        '        is_incoming = not getattr(msg, "outgoing", False)' + CRLF,
    ),
    # _on_dm_edit: имя переписки перестаёт участвовать в опознании HR
    (
        "backend/bot.py",
        '        chat_username = getattr(msg.chat, "username", None)' + CRLF,
        "        chat_username = None" + CRLF,
    ),
    # _on_dm_edit: своя правка тоже правит текст, ждущий разбора
    (
        "backend/bot.py",
        "        if updated and is_incoming:",
        "        if updated:",
    ),
    # _on_dm_delete: строка выбрасывается вместо пометки
    (
        "backend/bot.py",
        "                .values(is_deleted=True)",
        "                .values(is_deleted=False)",
    ),
    # _on_dm_delete: непрочитанное надгробие продолжает числиться
    (
        "backend/bot.py",
        "                .where(*where_clauses, Message.is_incoming,"
        " Message.read_at.is_(None))" + CRLF
        + "                .values(read_at=now)" + CRLF,
        "                .where(*where_clauses, Message.is_incoming,"
        " Message.read_at.is_(None))" + CRLF
        + "                .values()" + CRLF,
    ),
    # _on_dm_delete: безымянная уборка задевает и исходящие
    (
        "backend/bot.py",
        "                        Message.tg_message_id.in_(chatless_ids)," + CRLF
        + "                        Message.is_incoming," + CRLF
        + "                    ]," + CRLF,
        "                        Message.tg_message_id.in_(chatless_ids)," + CRLF
        + "                    ]," + CRLF,
    ),
    # _on_dm_delete: имя переписки перестаёт участвовать в опознании HR
    (
        "backend/bot.py",
        '                        chat_username = getattr(chat, "username", None)' + CRLF,
        "                        chat_username = None" + CRLF,
    ),
    # _on_dm_outgoing: эхо своей отправки пишется второй строкой
    (
        "backend/bot.py",
        "            if existing is not None:" + CRLF
        + "                # Echo собственного Bot.send-а",
        "            if False:" + CRLF + "                # Echo собственного Bot.send-а",
    ),
    # _on_dm_outgoing: выключенный бот всё равно подхватывает написанное
    (
        "backend/bot.py",
        "        if (await self._current_mode()) is BotMode.OFF:" + CRLF
        + "            return" + CRLF
        + "        if not msg.chat:" + CRLF
        + "            return" + CRLF
        + CRLF
        + "        recipient_id = msg.chat.id",
        "        if not msg.chat:" + CRLF
        + "            return" + CRLF
        + CRLF
        + "        recipient_id = msg.chat.id",
    ),
    # _on_dm_outgoing: имя получателя перестаёт участвовать в опознании HR
    (
        "backend/bot.py",
        '        recipient_username = getattr(msg.chat, "username", None)',
        "        recipient_username = None",
    ),
    # _on_dm: выключенный бот всё равно разбирает входящее
    (
        "backend/bot.py",
        "        # Off mode silences everything, including reading HR replies." + CRLF
        + "        if (await self._current_mode()) is BotMode.OFF:" + CRLF
        + "            return" + CRLF,
        "",
    ),
    # _on_dm: имя отправителя перестаёт участвовать в опознании HR
    (
        "backend/bot.py",
        "                    msg.from_user.id," + CRLF
        + "                    msg.from_user.username," + CRLF,
        "                    msg.from_user.id," + CRLF
        + "                    None," + CRLF,
    ),
]
