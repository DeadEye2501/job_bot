"""Поломки для обхода каналов в `backend/flows.py`.

Сводка названий, чтение новых сообщений, движение отметки и догон пропущенной
переписки.

Где поломка захватывает конец строки, перевод пишется через `CRLF`: рабочее
дерево здесь с виндовыми переводами, и поиск по `\\n` не находит ничего.
"""

CRLF = "\r\n"

MUTATIONS = [
    # poll_active_channels: настройки перестают перечитываться
    (
        "backend/flows.py",
        "        await self._reload_resources()" + CRLF
        + "        # Берём ВСЕ каналы",
        "        # Берём ВСЕ каналы",
    ),
    # poll_active_channels: канал без имени попадает в обход
    (
        "backend/flows.py",
        "                    select(TelegramChannel).where(" + CRLF
        + "                        TelegramChannel.username.is_not(None)" + CRLF
        + "                    )" + CRLF,
        "                    select(TelegramChannel)" + CRLF,
    ),
    # poll_active_channels: сообщения читаются и у выключенных каналов
    (
        "backend/flows.py",
        "        active_named = [c for c in all_named if c.is_active]",
        "        active_named = list(all_named)",
    ),
    # poll_active_channels: сводка названий не делается вовсе
    (
        "backend/flows.py",
        "        await self._refresh_channel_metadata(all_named)" + CRLF,
        "",
    ),
    # poll_active_channels: сорвавшийся канал роняет обход
    (
        "backend/flows.py",
        "            except Exception:" + CRLF
        + '                logger.exception("[@%s] poll failed", ch.username)' + CRLF,
        "            except ZeroDivisionError:" + CRLF
        + '                logger.exception("[@%s] poll failed", ch.username)' + CRLF,
    ),
    # poll_active_channels: полоса сообщений в окне не гасится
    (
        "backend/flows.py",
        '        self._emit_progress("message", "", 0, 0)' + CRLF,
        "",
    ),
    # poll_one_channel: канал без имени всё равно читается
    (
        "backend/flows.py",
        "            if ch is None or not ch.username:" + CRLF
        + "                return False" + CRLF,
        "            if ch is None:" + CRLF + "                return False" + CRLF,
    ),
    # poll_one_channel: сбой чтения выдаётся за успех
    (
        "backend/flows.py",
        '            logger.exception("[@%s] manual poll failed", username)' + CRLF
        + "            return False" + CRLF,
        '            logger.exception("[@%s] manual poll failed", username)' + CRLF
        + "            return True" + CRLF,
    ),
    # _refresh_channel_metadata: название переписывается и когда не менялось
    (
        "backend/flows.py",
        "            if new_title and new_title != ch.title:",
        "            if new_title:",
    ),
    # _refresh_channel_metadata: своя картинка канала затирается чужой
    (
        "backend/flows.py",
        '            if ch.avatar is None and getattr(chat, "photo", None) is not None:',
        '            if getattr(chat, "photo", None) is not None:',
    ),
    # _refresh_channel_metadata: недоступный канал обрывает сводку
    (
        "backend/flows.py",
        "            except Exception as e:" + CRLF
        + "                logger.warning(" + CRLF
        + '                    "[@%s] get_chat failed: %s: %s",' + CRLF,
        "            except ZeroDivisionError as e:" + CRLF
        + "                logger.warning(" + CRLF
        + '                    "[@%s] get_chat failed: %s: %s",' + CRLF,
    ),
    # _refresh_channel_metadata: удалённый канал воскрешается записью
    (
        "backend/flows.py",
        "                if db_ch is None:" + CRLF + "                    continue" + CRLF,
        "",
    ),
    # _refresh_channel_metadata: окно не узнаёт о свежих названиях
    (
        "backend/flows.py",
        "        if self.on_channels_changed is not None:" + CRLF
        + "            try:" + CRLF
        + "                self.on_channels_changed()" + CRLF,
        "        if False:" + CRLF
        + "            try:" + CRLF
        + "                self.on_channels_changed()" + CRLF,
    ),
    # refresh_channel_metadata_for_ids: пустой список всё равно идёт в сводку
    (
        "backend/flows.py",
        "        if not channel_ids:" + CRLF + "            return" + CRLF,
        "",
    ),
    # _poll_channel: чтение не обрывается на уже разобранном
    (
        "backend/flows.py",
        "            if last_id is not None and msg.id <= last_id:" + CRLF
        + "                break" + CRLF,
        "",
    ),
    # _poll_channel: сообщения разбираются от свежего к старому
    (
        "backend/flows.py",
        "        ordered = list(reversed(new_msgs))",
        "        ordered = list(new_msgs)",
    ),
    # _poll_channel: отметка не досохраняется после обрыва
    (
        "backend/flows.py",
        "        finally:" + CRLF
        + "            if cursor is not None:" + CRLF
        + "                await self._advance_cursor(channel_id, cursor)" + CRLF,
        "        finally:" + CRLF + "            pass" + CRLF,
    ),
    # _poll_channel: сломанное сообщение отметку не двигает
    (
        "backend/flows.py",
        "                cursor = msg.id" + CRLF,
        "",
    ),
    # _advance_cursor: отметка по удалённому каналу заводится заново
    (
        "backend/flows.py",
        "            if ch is None:" + CRLF + "                return" + CRLF
        + "            ch.last_processed_msg_id = msg_id" + CRLF,
        "            ch.last_processed_msg_id = msg_id" + CRLF,
    ),
    # backfill: HR без адреса всё равно идёт в догон
    (
        "backend/flows.py",
        "    if target is None:" + CRLF + "        return" + CRLF + "    messages = []",
        "    messages = []",
    ),
    # backfill: переписка кладётся от свежего к старому
    (
        "backend/flows.py",
        "    for msg in reversed(messages):",
        "    for msg in messages:",
    ),
    # backfill: удалённое за время простоя не метится
    (
        "backend/flows.py",
        "                row.is_deleted = True" + CRLF,
        "",
    ),
    # backfill: удалённым метят и то, что старше вытянутого окна
    (
        "backend/flows.py",
        "                            Message.tg_message_id >= min_id," + CRLF,
        "",
    ),
    # backfill: пустой ответ Telegram метит всю переписку удалённой
    (
        "backend/flows.py",
        "    if messages:" + CRLF + "        seen_ids = {m.id for m in messages}",
        "    if True:" + CRLF + "        seen_ids = {m.id for m in messages}",
    ),
    # backfill: окно не узнаёт о догнанной переписке
    (
        "backend/flows.py",
        "    if (had_new or tombstoned) and on_message_persisted is not None:",
        "    if False:",
    ),
    # backfill: окно дёргают и когда ничего не изменилось
    (
        "backend/flows.py",
        "    if (had_new or tombstoned) and on_message_persisted is not None:",
        "    if on_message_persisted is not None:",
    ),
    # catch_up: пачки идут без паузы между собой
    (
        "backend/flows.py",
        "        if batch_start + _DM_CATCHUP_BATCH_SIZE < len(chats):" + CRLF
        + "            await asyncio.sleep(_DM_CATCHUP_BATCH_DELAY_SEC)" + CRLF,
        "",
    ),
    # catch_up: сорвавшаяся переписка роняет пачку
    (
        "backend/flows.py",
        "            return_exceptions=True," + CRLF
        + "        )" + CRLF
        + "        for (hr, _), result in zip(batch, results):",
        "            return_exceptions=False," + CRLF
        + "        )" + CRLF
        + "        for (hr, _), result in zip(batch, results):",
    ),
]
