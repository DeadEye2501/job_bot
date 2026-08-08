"""Вторая половина поломок для `backend/bot.py`.

Отделена от `bot.py` не по предмету, а по ходу прохода: первый набор дошёл до
конца главного цикла и был прерван, а шесть поломок в нём не совпали с
исходником или совпали не единожды. Здесь они переписаны и дополнены
остатком.
"""

CRLF = "\r\n"

MUTATIONS = [
    # _looks_like_photo: непринимаемое расширение перестаёт отсеиваться
    (
        "backend/bot.py",
        "    if suffix not in PHOTO_EXTS:" + CRLF + "        return False" + CRLF,
        "",
    ),
    # _looks_like_photo: регистр расширения перестаёт опускаться
    (
        "backend/bot.py",
        "    suffix = path.suffix.lower()",
        "    suffix = path.suffix",
    ),
    # _looks_like_photo: переименованный файл перестаёт опознаваться по виду
    (
        "backend/bot.py",
        '    return bool(mime and mime.startswith("image/"))',
        "    return True",
    ),
    # _shares_provider: ключ перестаёт сравниваться
    (
        "backend/bot.py",
        "        and a.base_url == b.base_url" + CRLF
        + "        and a.api_key == b.api_key" + CRLF,
        "        and a.base_url == b.base_url" + CRLF,
    ),
    # _shares_provider: отсутствие настройки перестаёт разводить клиентов
    (
        "backend/bot.py",
        "        a is not None" + CRLF + "        and b is not None" + CRLF,
        "",
    ),
    # kick: без живого цикла побудка теряется
    (
        "backend/bot.py",
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
    # kick: побудка на живом цикле уходит мимо него
    (
        "backend/bot.py",
        '        logger.debug("Poll wake requested")' + CRLF
        + "        loop = self._loop" + CRLF
        + "        if loop is not None and not loop.is_closed():" + CRLF
        + "            loop.call_soon_threadsafe(self._wake_event.set)" + CRLF,
        '        logger.debug("Poll wake requested")' + CRLF
        + "        loop = self._loop" + CRLF
        + "        if loop is not None and not loop.is_closed():" + CRLF
        + "            pass" + CRLF,
    ),
    # _on_dm_outgoing: эхо своей отправки пишется второй строкой
    (
        "backend/bot.py",
        "            if existing is not None:" + CRLF
        + "                # Echo собственного Bot.send-а",
        "            if False:" + CRLF
        + "                # Echo собственного Bot.send-а",
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
