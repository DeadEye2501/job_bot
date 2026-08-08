"""Поломки для `backend/bot.py`.

Где поломка захватывает конец строки, перевод пишется через `CRLF`: рабочее
дерево здесь с виндовыми переводами, и поиск по `\\n` не находит ничего.
"""

CRLF = "\r\n"

MUTATIONS = [
    # _looks_like_photo: список принимаемых расширений теряет одно
    (
        "backend/bot.py",
        'PHOTO_EXTS = {".png", ".jpg", ".jpeg", ".webp"}',
        'PHOTO_EXTS = {".png", ".jpg", ".jpeg"}',
    ),
    # _looks_like_photo: регистр расширения перестаёт опускаться
    (
        "backend/bot.py",
        "    return path.suffix.lower() in PHOTO_EXTS",
        "    return path.suffix in PHOTO_EXTS",
    ),
    # _media_cache_path: номер собеседника выпадает из пути
    (
        "backend/bot.py",
        '    return MEDIA_DIR / str(hr_id) / f"{tg_message_id}{ext}"',
        '    return MEDIA_DIR / f"{tg_message_id}{ext}"',
    ),
    # _media_path_for_db: путь пишется целиком, а не относительно папки
    (
        "backend/bot.py",
        "        return p.relative_to(MEDIA_DIR.resolve()).as_posix()",
        "        return p.as_posix()",
    ),
    # _shares_provider: ключ перестаёт сравниваться
    (
        "backend/bot.py",
        "    return a.base_url == b.base_url and a.api_key == b.api_key",
        "    return a.base_url == b.base_url",
    ),
    # _shares_provider: сравнивается ещё и модель
    (
        "backend/bot.py",
        "    return a.base_url == b.base_url and a.api_key == b.api_key",
        "    return (a.base_url == b.base_url and a.api_key == b.api_key"
        " and a.model == b.model)",
    ),
    # _download_media: картинка получает расширение документа
    (
        "backend/bot.py",
        '        ext = ".jpg"  # Pyrogram delivers photos as JPEGs',
        '        ext = ".bin"',
    ),
    # _download_media: уже скачанный файл качается заново
    (
        "backend/bot.py",
        "    if out.exists():" + CRLF + "        return _media_path_for_db(out)" + CRLF,
        "",
    ),
    # _download_media: сбой скачивания перестаёт быть отсутствием
    (
        "backend/bot.py",
        "    if not path:" + CRLF + "        return None" + CRLF,
        "",
    ),
    # kick: побудка на живом цикле уходит мимо него
    (
        "backend/bot.py",
        "        loop.call_soon_threadsafe(self._wake_event.set)",
        "        pass",
    ),
    # kick: без живого цикла побудка теряется
    (
        "backend/bot.py",
        "    if loop is not None and not loop.is_closed():" + CRLF
        + "        loop.call_soon_threadsafe(self._wake_event.set)" + CRLF
        + "    else:" + CRLF
        + "        self._wake_event.set()" + CRLF,
        "    if loop is not None and not loop.is_closed():" + CRLF
        + "        loop.call_soon_threadsafe(self._wake_event.set)" + CRLF,
    ),
    # request_stop: остановка перестаёт будить цикл
    (
        "backend/bot.py",
        "            self._stop_event.set()" + CRLF
        + "            self._wake_event.set()" + CRLF,
        "            self._stop_event.set()" + CRLF,
    ),
    # cancel_current_poll: завершённая задача всё равно отменяется
    (
        "backend/bot.py",
        "        if task is None or task.done():",
        "        if task is None:",
    ),
    # poll_channel_now: занятое место перестаёт отбивать второй прогон
    (
        "backend/bot.py",
        '                "poll_channel_now: another cycle is running, skipping'
        ' (channel_id=%d)",' + CRLF
        + "                channel_id," + CRLF
        + "            )" + CRLF
        + '            return "busy"' + CRLF,
        '                "poll_channel_now: another cycle is running, skipping'
        ' (channel_id=%d)",' + CRLF
        + "                channel_id," + CRLF
        + "            )" + CRLF,
    ),
    # poll_channel_now: отказ конвейера перестаёт быть «не найден»
    (
        "backend/bot.py",
        "                if not ok:" + CRLF + '                    status = "missing"' + CRLF,
        "",
    ),
    # poll_channel_now: место не освобождается после прогона
    (
        "backend/bot.py",
        "            self._current_poll_task = None" + CRLF
        + "            if self.on_cycle_end is not None:" + CRLF
        + '                try: self.on_cycle_end()' + CRLF
        + '                except Exception: logger.exception("on_cycle_end hook failed")' + CRLF
        + '        return status' + CRLF
        + CRLF
        + "    async def reset_channel_cursor",
        "            if self.on_cycle_end is not None:" + CRLF
        + '                try: self.on_cycle_end()' + CRLF
        + '                except Exception: logger.exception("on_cycle_end hook failed")' + CRLF
        + '        return status' + CRLF
        + CRLF
        + "    async def reset_channel_cursor",
    ),
    # add_channel: повтор до обращения к Telegram перестаёт находиться
    (
        "backend/bot.py",
        "        async with self._session_factory() as session:" + CRLF
        + "            existing = await repository.find_channel_by_username(session, username)" + CRLF
        + "            if existing is not None:" + CRLF
        + '                return existing.id, "exists"' + CRLF,
        "",
    ),
    # add_channel: повтор после обращения перестаёт находиться
    (
        "backend/bot.py",
        "                existing = await repository.find_channel_by_username(session, username)" + CRLF
        + "                if existing is not None:" + CRLF
        + '                    return existing.id, "exists"' + CRLF,
        "",
    ),
    # add_channel: имя перестаёт опускаться в строчные
    (
        "backend/bot.py",
        "                    username=username.lower(),",
        "                    username=username,",
    ),
    # add_channel: аватар тянется и у канала без картинки
    (
        "backend/bot.py",
        '            if getattr(chat, "photo", None) is not None' + CRLF
        + "            else None" + CRLF,
        "            if True" + CRLF + "            else None" + CRLF,
    ),
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
        + '                "Bot.send: BotMode.OFF, suppressed send to %s (vacancy=%s)",' + CRLF,
        "        if False:" + CRLF
        + "            logger.warning(" + CRLF
        + '                "Bot.send: BotMode.OFF, suppressed send to %s (vacancy=%s)",' + CRLF,
    ),
    # send: чёрный список перестаёт отбивать отправку
    (
        "backend/bot.py",
        "        if bl_value:" + CRLF
        + "            logger.warning(" + CRLF
        + '                "Bot.send: hr %s in blacklist (%s), suppressed (vacancy=%s)",' + CRLF,
        "        if False:" + CRLF
        + "            logger.warning(" + CRLF
        + '                "Bot.send: hr %s in blacklist (%s), suppressed (vacancy=%s)",' + CRLF,
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
    # send: заглушенная отправка всё равно пишет сообщение в переписку
    (
        "backend/bot.py",
        "                if not suppressed:" + CRLF
        + "                    session.add(",
        "                if True:" + CRLF
        + "                    session.add(",
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
    # _on_raw_update: чужие оповещения перестают отсеиваться
    (
        "backend/bot.py",
        "        if not isinstance(update, _UpdateReadHistoryOutbox):" + CRLF
        + "            return" + CRLF,
        "",
    ),
    # _on_raw_update: групповые чаты перестают отсеиваться
    (
        "backend/bot.py",
        "        if not isinstance(peer, _PeerUser):" + CRLF
        + "            return" + CRLF,
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
    # send_to_hr_media: картинка уходит документом
    (
        "backend/bot.py",
        "        if as_photo:" + CRLF
        + "            pyro_msg = await self._client.send_photo(target, str(src))" + CRLF
        + "        else:" + CRLF
        + "            pyro_msg = await self._client.send_document(target, str(src))" + CRLF,
        "        pyro_msg = await self._client.send_document(target, str(src))" + CRLF,
    ),
    # send_to_hr_media: предел размера перестаёт зависеть от вида файла
    (
        "backend/bot.py",
        "        cap = PHOTO_SIZE_LIMIT if as_photo else DOCUMENT_SIZE_LIMIT",
        "        cap = DOCUMENT_SIZE_LIMIT",
    ),
    # send_to_hr_media: предел становится исключающим
    (
        "backend/bot.py",
        "        if size > cap:",
        "        if size >= cap:",
    ),
    # send_to_hr_media: имя запоминается и у картинки
    (
        "backend/bot.py",
        "        media_name = None if as_photo else src.name",
        "        media_name = src.name",
    ),
    # send_to_hr_media: несуществующий путь перестаёт отбиваться
    (
        "backend/bot.py",
        "        if not src.exists() or not src.is_file():" + CRLF
        + '            raise RuntimeError(f"Файл не найден: {file_path}")' + CRLF,
        "",
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
        "                .where(*where_clauses, Message.is_incoming, Message.read_at.is_(None))" + CRLF
        + "                .values(read_at=now)" + CRLF,
        "                .where(*where_clauses, Message.is_incoming, Message.read_at.is_(None))" + CRLF
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
    # _on_dm_outgoing: эхо своей отправки пишется второй строкой
    (
        "backend/bot.py",
        "            if existing is not None:" + CRLF,
        "            if False:" + CRLF,
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
    # _on_dm: выключенный бот всё равно разбирает входящее
    (
        "backend/bot.py",
        "        # Off mode silences everything, including reading HR replies." + CRLF
        + "        if (await self._current_mode()) is BotMode.OFF:" + CRLF
        + "            return" + CRLF,
        "",
    ),
    # _on_dm: об окне сообщают и при неизвестном отправителе
    (
        "backend/bot.py",
        "        if not msg.from_user:" + CRLF + "            return" + CRLF,
        "",
    ),
    # _persist_session_if_changed: совпавшая строка всё равно переписывается
    (
        "backend/bot.py",
        '        if new_str == (tg.session_string or ""):' + CRLF
        + "            return" + CRLF,
        "",
    ),
    # _current_mode: сбой чтения режима даёт полный вместо выключенного
    (
        "backend/bot.py",
        "            return BotMode.OFF" + CRLF
        + CRLF
        + "    async def run(self, *, once: bool = False) -> None:",
        "            return BotMode.FULL" + CRLF
        + CRLF
        + "    async def run(self, *, once: bool = False) -> None:",
    ),
    # run: готовность объявляется до подключения клиента
    (
        "backend/bot.py",
        "        await self._client.start()" + CRLF,
        "        self._loop = asyncio.get_running_loop()" + CRLF
        + "        await self._client.start()" + CRLF,
    ),
    # run: недоразобранные вакансии не подбираются
    (
        "backend/bot.py",
        "                await self._ingestion.recover_orphan_vacancies()",
        "                pass",
    ),
    # run: слив ждущего разбора при выключении пропадает
    (
        "backend/bot.py",
        "                    await self._ingestion.cancel_pending_dm_classifications(drain=True)",
        "                    pass",
    ),
    # run: догон пропущенных писем не делается
    (
        "backend/bot.py",
        "                if mode is not BotMode.OFF and prev_mode is BotMode.OFF:",
        "                if False:",
    ),
    # run: проверка молчания HR идёт и в выключенном режиме
    (
        "backend/bot.py",
        "                if mode is not BotMode.OFF:" + CRLF
        + "                    try:" + CRLF
        + "                        await self._ingestion.check_ghosting_timeouts()" + CRLF,
        "                if True:" + CRLF
        + "                    try:" + CRLF
        + "                        await self._ingestion.check_ghosting_timeouts()" + CRLF,
    ),
    # run: по каналам ходят и в режиме «только личные»
    (
        "backend/bot.py",
        "                if mode is BotMode.FULL and self._current_poll_task is None:",
        "                if self._current_poll_task is None:",
    ),
    # run: идущий ручной прогон перебивается оборотом
    (
        "backend/bot.py",
        "                if mode is BotMode.FULL and self._current_poll_task is None:",
        "                if mode is BotMode.FULL:",
    ),
    # run: признак остановки ставится после отключения клиента
    (
        "backend/bot.py",
        "            self._ingestion.mark_shutting_down()",
        "            pass",
    ),
    # run: общее соединение с моделью закрывается дважды
    (
        "backend/bot.py",
        "            if self._lm_embed_client is not self._lm_client:" + CRLF
        + "                await self._lm_embed_client.aclose()" + CRLF,
        "            await self._lm_embed_client.aclose()" + CRLF,
    ),
    # run: соединение с моделью не закрывается вовсе
    (
        "backend/bot.py",
        "            await self._lm_client.aclose()",
        "            pass",
    ),
]
