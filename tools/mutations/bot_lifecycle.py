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
        + "        runner_loop = self._loop" + CRLF
        + "        if runner_loop is not None and not runner_loop.is_closed():" + CRLF
        + "            runner_loop.call_soon_threadsafe(self._wake_event.set)" + CRLF,
        '        logger.debug("Poll wake requested")' + CRLF
        + "        runner_loop = self._loop" + CRLF
        + "        if runner_loop is not None and not runner_loop.is_closed():" + CRLF
        + "            pass" + CRLF,
    ),
    # kick: без живого цикла побудка теряется
    (
        "backend/bot/client.py",
        "        if runner_loop is not None and not runner_loop.is_closed():" + CRLF
        + "            runner_loop.call_soon_threadsafe(self._wake_event.set)" + CRLF
        + "        else:" + CRLF
        + "            self._wake_event.set()" + CRLF
        + CRLF
        + CRLF
        + "    def request_stop(",
        "        if runner_loop is not None and not runner_loop.is_closed():" + CRLF
        + "            runner_loop.call_soon_threadsafe(self._wake_event.set)" + CRLF
        + CRLF
        + CRLF
        + "    def request_stop(",
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
        "backend/bot/channels.py",
        "        loop.call_soon_threadsafe(task.cancel)" + CRLF
        + "    else:" + CRLF
        + "        task.cancel()" + CRLF,
        "        pass" + CRLF + "    else:" + CRLF + "        pass" + CRLF,
    ),
    # run_in_slot: занятое место перестаёт отбивать второй прогон
    (
        "backend/bot/slot.py",
        '        logger.info("%s: another cycle is already running, skipping", label)'
        + CRLF
        + '        return "busy", None' + CRLF,
        '        logger.info("%s: another cycle is already running, skipping", label)'
        + CRLF,
    ),
    # poll_channel_now: обход канала начинает трогать полосу прогресса
    (
        "backend/bot/channels.py",
        '        f"manual poll for channel {channel_id}",' + CRLF + "    )" + CRLF,
        '        f"manual poll for channel {channel_id}",' + CRLF
        + '        progress=("poll", "", 0, 0),' + CRLF
        + "    )" + CRLF,
    ),
    # poll_channel_now: отказ конвейера перестаёт быть «не найден»
    (
        "backend/bot/channels.py",
        '    if outcome == "ok" and not ok:' + CRLF
        + '        return "missing"' + CRLF,
        "",
    ),
    # run_in_slot: место не освобождается после прогона
    (
        "backend/bot/slot.py",
        "        bot._current_poll_task = None" + CRLF
        + '        fire(bot.on_cycle_end, "on_cycle_end")' + CRLF,
        '        fire(bot.on_cycle_end, "on_cycle_end")' + CRLF,
    ),
    # add_channel: повтор до обращения к Telegram перестаёт находиться
    (
        "backend/bot/channels.py",
        "    async with bot._session_factory() as session:" + CRLF
        + "        existing = await find_channel_by_username("     "session, username)" + CRLF
        + "        if existing is not None:" + CRLF
        + '            return existing.id, "exists"' + CRLF,
        "",
    ),
    # add_channel: повтор после обращения перестаёт находиться
    (
        "backend/bot/channels.py",
        "            existing = await find_channel_by_username("     "session, username)" + CRLF
        + "            if existing is not None:" + CRLF
        + '                return existing.id, "exists"' + CRLF,
        "",
    ),
    # add_channel: имя перестаёт опускаться в строчные
    (
        "backend/bot/channels.py",
        "                username=username.lower(),",
        "                username=username,",
    ),
    # persist_session_if_changed: совпавшая строка всё равно переписывается
    (
        "backend/bot/loop.py",
        '    if new_str == (tg.session_string or ""):' + CRLF
        + "        return" + CRLF,
        "",
    ),
    # current_mode: сбой чтения режима даёт полный вместо выключенного
    (
        "backend/bot/loop.py",
        '        logger.exception("get_mode failed; falling back to Off")' + CRLF
        + "        return BotMode.OFF",
        '        logger.exception("get_mode failed; falling back to Off")' + CRLF
        + "        return BotMode.FULL",
    ),
    # run: готовность объявляется до подключения клиента
    (
        "backend/bot/loop.py",
        "    await bot._client.start()" + CRLF,
        "    bot._loop = asyncio.get_running_loop()" + CRLF
        + "    await bot._client.start()" + CRLF,
    ),
    # run: недоразобранные вакансии не подбираются
    (
        "backend/bot/loop.py",
        "            await bot._ingestion.recover_orphan_vacancies()",
        "            pass",
    ),
    # run: слив ждущего разбора при выключении пропадает
    (
        "backend/bot/loop.py",
        "                await bot._ingestion.cancel_pending_dm_classifications("     "drain=True)",
        "                pass",
    ),
    # run: догон пропущенных писем не делается
    (
        "backend/bot/loop.py",
        "            if mode is not BotMode.OFF and prev_mode is BotMode.OFF:",
        "            if False:",
    ),
    # run: проверка молчания HR идёт и в выключенном режиме
    (
        "backend/bot/loop.py",
        "            if mode is not BotMode.OFF:" + CRLF
        + "                try:" + CRLF
        + "                    await bot._ingestion.check_ghosting_timeouts()" + CRLF,
        "            if True:" + CRLF
        + "                try:" + CRLF
        + "                    await bot._ingestion.check_ghosting_timeouts()" + CRLF,
    ),
    # run: по каналам ходят и в режиме «только личные»
    (
        "backend/bot/loop.py",
        "            if mode is BotMode.FULL:" + CRLF,
        "            if True:" + CRLF,
    ),
    # run: признак остановки ставится после отключения клиента
    (
        "backend/bot/loop.py",
        "        bot._ingestion.mark_shutting_down()",
        "        pass",
    ),
    # run: общее соединение с моделью закрывается дважды
    (
        "backend/bot/loop.py",
        "        if bot._lm_embed_client is not bot._lm_client:" + CRLF
        + "            await bot._lm_embed_client.aclose()" + CRLF,
        "        await bot._lm_embed_client.aclose()" + CRLF,
    ),
    # run: соединение с моделью не закрывается вовсе
    (
        "backend/bot/loop.py",
        "        await bot._lm_client.aclose()",
        "        pass",
    ),
]
