"""Остаток поломок для `backend/bot.py`: главный цикл и род оповещения.

Второй набор оборвался на первой же поломке главного цикла — снятый слив
вешал прогон, потому что цикл в проверке кончался этим самым сливом. Проверка
переписана, поломки перенесены сюда.
"""

CRLF = "\r\n"

MUTATIONS = [
    # _on_raw_update: чужой род оповещения перестаёт отсеиваться
    (
        "backend/bot.py",
        "        if not isinstance(update, _UpdateReadHistoryOutbox):" + CRLF
        + "            return" + CRLF,
        "",
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
