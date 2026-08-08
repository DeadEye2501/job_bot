"""Поломки для жизни бота: сигналы, каналы, место прогона, оборот цикла.

Где поломка захватывает конец строки, перевод пишется через `CRLF`: рабочее
дерево здесь с виндовыми переводами, и поиск по `\\n` не находит ничего.
"""

CRLF = "\r\n"

MUTATIONS = [
    # kick: побудка на живом цикле уходит мимо него
    (
        "backend/bot/client.py",
        '        logger.debug("Poll wake requested")' + CRLF
        + "        loop = self._loop" + CRLF
        + "        if loop is not None and not loop.is_closed():" + CRLF
        + "            loop.call_soon_threadsafe(self._wake_event.set)" + CRLF,
        '        logger.debug("Poll wake requested")' + CRLF
        + "        loop = self._loop" + CRLF
        + "        if loop is not None and not loop.is_closed():" + CRLF
        + "            pass" + CRLF,
    ),
    # kick: без живого цикла побудка теряется
    (
        "backend/bot/client.py",
        "        if loop is not None and not loop.is_closed():" + CRLF
        + "            loop.call_soon_threadsafe(self._wake_event.set)" + CRLF
        + "        else:" + CRLF
        + "            self._wake_event.set()" + CRLF
        + CRLF
        + "    async def poll_channel_now(",
        "        if loop is not None and not loop.is_closed():" + CRLF
        + "            loop.call_soon_threadsafe(self._wake_event.set)" + CRLF
        + CRLF
        + "    async def poll_channel_now(",
    ),
    # request_stop: остановка перестаёт будить цикл
    (
        "backend/bot/client.py",
        "            self._stop_event.set()" + CRLF
        + "            self._wake_event.set()" + CRLF,
        "            self._stop_event.set()" + CRLF,
    ),
    # cancel_current_poll: отмена не доходит до задачи
    (
        "backend/bot/client.py",
        "            loop.call_soon_threadsafe(task.cancel)" + CRLF
        + "        else:" + CRLF
        + "            task.cancel()" + CRLF,
        "            pass" + CRLF + "        else:" + CRLF + "            pass" + CRLF,
    ),
    # poll_channel_now: занятое место перестаёт отбивать второй прогон
    (
        "backend/bot/client.py",
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
        "backend/bot/client.py",
        "                if not ok:" + CRLF
        + '                    status = "missing"' + CRLF,
        "",
    ),
    # poll_channel_now: место не освобождается после прогона
    (
        "backend/bot/client.py",
        "            self._current_poll_task = None" + CRLF
        + "            if self.on_cycle_end is not None:" + CRLF
        + "                try: self.on_cycle_end()" + CRLF
        + '                except Exception: logger.exception("on_cycle_end hook failed")'
        + CRLF
        + "        return status" + CRLF
        + CRLF
        + "    async def reset_channel_cursor",
        "            if self.on_cycle_end is not None:" + CRLF
        + "                try: self.on_cycle_end()" + CRLF
        + '                except Exception: logger.exception("on_cycle_end hook failed")'
        + CRLF
        + "        return status" + CRLF
        + CRLF
        + "    async def reset_channel_cursor",
    ),
    # add_channel: повтор до обращения к Telegram перестаёт находиться
    (
        "backend/bot/client.py",
        "        async with self._session_factory() as session:" + CRLF
        + "            existing = await repository.find_channel_by_username("
        "session, username)" + CRLF
        + "            if existing is not None:" + CRLF
        + '                return existing.id, "exists"' + CRLF,
        "",
    ),
    # add_channel: повтор после обращения перестаёт находиться
    (
        "backend/bot/client.py",
        "                existing = await repository.find_channel_by_username("
        "session, username)" + CRLF
        + "                if existing is not None:" + CRLF
        + '                    return existing.id, "exists"' + CRLF,
        "",
    ),
    # add_channel: имя перестаёт опускаться в строчные
    (
        "backend/bot/client.py",
        "                    username=username.lower(),",
        "                    username=username,",
    ),
    # _persist_session_if_changed: совпавшая строка всё равно переписывается
    (
        "backend/bot/client.py",
        '        if new_str == (tg.session_string or ""):' + CRLF
        + "            return" + CRLF,
        "",
    ),
    # _current_mode: сбой чтения режима даёт полный вместо выключенного
    (
        "backend/bot/client.py",
        "            return BotMode.OFF" + CRLF
        + CRLF
        + "    async def run(self, *, once: bool = False) -> None:",
        "            return BotMode.FULL" + CRLF
        + CRLF
        + "    async def run(self, *, once: bool = False) -> None:",
    ),
    # run: готовность объявляется до подключения клиента
    (
        "backend/bot/client.py",
        "        await self._client.start()" + CRLF,
        "        self._loop = asyncio.get_running_loop()" + CRLF
        + "        await self._client.start()" + CRLF,
    ),
    # run: недоразобранные вакансии не подбираются
    (
        "backend/bot/client.py",
        "                await self._ingestion.recover_orphan_vacancies()",
        "                pass",
    ),
    # run: слив ждущего разбора при выключении пропадает
    (
        "backend/bot/client.py",
        "                    await self._ingestion.cancel_pending_dm_classifications("
        "drain=True)",
        "                    pass",
    ),
    # run: догон пропущенных писем не делается
    (
        "backend/bot/client.py",
        "                if mode is not BotMode.OFF and prev_mode is BotMode.OFF:",
        "                if False:",
    ),
    # run: проверка молчания HR идёт и в выключенном режиме
    (
        "backend/bot/client.py",
        "                if mode is not BotMode.OFF:" + CRLF
        + "                    try:" + CRLF
        + "                        await self._ingestion.check_ghosting_timeouts()" + CRLF,
        "                if True:" + CRLF
        + "                    try:" + CRLF
        + "                        await self._ingestion.check_ghosting_timeouts()" + CRLF,
    ),
    # run: по каналам ходят и в режиме «только личные»
    (
        "backend/bot/client.py",
        "                if mode is BotMode.FULL and self._current_poll_task is None:",
        "                if self._current_poll_task is None:",
    ),
    # run: идущий ручной прогон перебивается оборотом
    (
        "backend/bot/client.py",
        "                if mode is BotMode.FULL and self._current_poll_task is None:",
        "                if mode is BotMode.FULL:",
    ),
    # run: признак остановки ставится после отключения клиента
    (
        "backend/bot/client.py",
        "            self._ingestion.mark_shutting_down()",
        "            pass",
    ),
    # run: общее соединение с моделью закрывается дважды
    (
        "backend/bot/client.py",
        "            if self._lm_embed_client is not self._lm_client:" + CRLF
        + "                await self._lm_embed_client.aclose()" + CRLF,
        "            await self._lm_embed_client.aclose()" + CRLF,
    ),
    # run: соединение с моделью не закрывается вовсе
    (
        "backend/bot/client.py",
        "            await self._lm_client.aclose()",
        "            pass",
    ),
]
