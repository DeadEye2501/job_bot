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
        "backend/flows/pipeline.py",
        "        await self._reload_resources()" + CRLF
        + "        # Берём ВСЕ каналы",
        "        # Берём ВСЕ каналы",
    ),
    # poll_active_channels: канал без имени попадает в обход
    (
        "backend/flows/pipeline.py",
        "                    select(TelegramChannel).where(" + CRLF
        + "                        TelegramChannel.username.is_not(None)" + CRLF
        + "                    )" + CRLF,
        "                    select(TelegramChannel)" + CRLF,
    ),
    # poll_active_channels: сообщения читаются и у выключенных каналов
    (
        "backend/flows/pipeline.py",
        "        active_named = [c for c in all_named if c.is_active]",
        "        active_named = list(all_named)",
    ),
    # poll_active_channels: сводка названий не делается вовсе
    (
        "backend/flows/pipeline.py",
        "        await self._refresh_channel_metadata(all_named)" + CRLF,
        "",
    ),
    # poll_active_channels: сорвавшийся канал роняет обход
    (
        "backend/flows/pipeline.py",
        "            except Exception:" + CRLF
        + '                logger.exception("[@%s] poll failed", ch.username)' + CRLF,
        "            except ZeroDivisionError:" + CRLF
        + '                logger.exception("[@%s] poll failed", ch.username)' + CRLF,
    ),
    # poll_active_channels: полоса сообщений в окне не гасится
    (
        "backend/flows/pipeline.py",
        '        self._emit_progress("message", "", 0, 0)' + CRLF,
        "",
    ),
    # poll_one_channel: канал без имени всё равно читается
    (
        "backend/flows/pipeline.py",
        "            if ch is None or not ch.username:" + CRLF
        + "                return False" + CRLF,
        "            if ch is None:" + CRLF + "                return False" + CRLF,
    ),
    # poll_one_channel: сбой чтения выдаётся за успех
    (
        "backend/flows/pipeline.py",
        '            logger.exception("[@%s] manual poll failed", username)' + CRLF
        + "            return False" + CRLF,
        '            logger.exception("[@%s] manual poll failed", username)' + CRLF
        + "            return True" + CRLF,
    ),
    # _refresh_channel_metadata: название переписывается и когда не менялось
    (
        "backend/flows/pipeline.py",
        "            if new_title and new_title != ch.title:",
        "            if new_title:",
    ),
    # _refresh_channel_metadata: своя картинка канала затирается чужой
    (
        "backend/flows/pipeline.py",
        '            if ch.avatar is None and getattr(chat, "photo", None) is not None:',
        '            if getattr(chat, "photo", None) is not None:',
    ),
    # _refresh_channel_metadata: недоступный канал обрывает сводку
    (
        "backend/flows/pipeline.py",
        "            except Exception as e:" + CRLF
        + "                logger.warning(" + CRLF
        + '                    "[@%s] get_chat failed: %s: %s",' + CRLF,
        "            except ZeroDivisionError as e:" + CRLF
        + "                logger.warning(" + CRLF
        + '                    "[@%s] get_chat failed: %s: %s",' + CRLF,
    ),
    # _refresh_channel_metadata: удалённый канал воскрешается записью
    (
        "backend/flows/pipeline.py",
        "                if db_ch is None:" + CRLF + "                    continue" + CRLF,
        "",
    ),
    # _refresh_channel_metadata: окно не узнаёт о свежих названиях
    (
        "backend/flows/pipeline.py",
        "        if self.on_channels_changed is not None:" + CRLF
        + "            try:" + CRLF
        + "                self.on_channels_changed()" + CRLF,
        "        if False:" + CRLF
        + "            try:" + CRLF
        + "                self.on_channels_changed()" + CRLF,
    ),
    # refresh_channel_metadata_for_ids: пустой список всё равно идёт в сводку
    (
        "backend/flows/pipeline.py",
        "        if not channel_ids:" + CRLF + "            return" + CRLF,
        "",
    ),
    # _poll_channel: чтение не обрывается на уже разобранном
    (
        "backend/flows/pipeline.py",
        "            if last_id is not None and msg.id <= last_id:" + CRLF
        + "                break" + CRLF,
        "",
    ),
    # _poll_channel: сообщения разбираются от свежего к старому
    (
        "backend/flows/pipeline.py",
        "        ordered = list(reversed(new_msgs))",
        "        ordered = list(new_msgs)",
    ),
    # _poll_channel: отметка не досохраняется после обрыва
    (
        "backend/flows/pipeline.py",
        "        finally:" + CRLF
        + "            if cursor is not None:" + CRLF
        + "                await self._advance_cursor(channel_id, cursor)" + CRLF,
        "        finally:" + CRLF + "            pass" + CRLF,
    ),
    # _poll_channel: сломанное сообщение отметку не двигает
    (
        "backend/flows/pipeline.py",
        "                cursor = msg.id" + CRLF,
        "",
    ),
    # _advance_cursor: отметка по удалённому каналу заводится заново
    (
        "backend/flows/pipeline.py",
        "            if ch is None:" + CRLF + "                return" + CRLF
        + "            ch.last_processed_msg_id = msg_id" + CRLF,
        "            ch.last_processed_msg_id = msg_id" + CRLF,
    ),
    # backfill: HR без адреса всё равно идёт в догон
    (
        "backend/flows/pipeline.py",
        "    if target is None:" + CRLF + "        return" + CRLF + "    messages = []",
        "    messages = []",
    ),
    # backfill: переписка кладётся от свежего к старому
    (
        "backend/flows/pipeline.py",
        "    for msg in reversed(messages):",
        "    for msg in messages:",
    ),
    # backfill: удалённое за время простоя не метится
    (
        "backend/flows/pipeline.py",
        "                row.is_deleted = True" + CRLF,
        "",
    ),
    # backfill: удалённым метят и то, что старше вытянутого окна
    (
        "backend/flows/pipeline.py",
        "                            Message.tg_message_id >= min_id," + CRLF,
        "",
    ),
    # backfill: пустой ответ Telegram метит всю переписку удалённой
    (
        "backend/flows/pipeline.py",
        "    if messages:" + CRLF + "        seen_ids = {m.id for m in messages}",
        "    if True:" + CRLF + "        seen_ids = {m.id for m in messages}",
    ),
    # backfill: окно не узнаёт о догнанной переписке
    (
        "backend/flows/pipeline.py",
        "    if (had_new or tombstoned) and on_message_persisted is not None:",
        "    if False:",
    ),
    # backfill: окно дёргают и когда ничего не изменилось
    (
        "backend/flows/pipeline.py",
        "    if (had_new or tombstoned) and on_message_persisted is not None:",
        "    if on_message_persisted is not None:",
    ),
    # catch_up: пачки идут без паузы между собой
    (
        "backend/flows/pipeline.py",
        "        if batch_start + _DM_CATCHUP_BATCH_SIZE < len(chats):" + CRLF
        + "            await asyncio.sleep(_DM_CATCHUP_BATCH_DELAY_SEC)" + CRLF,
        "",
    ),
    # catch_up: сорвавшаяся переписка роняет пачку
    (
        "backend/flows/pipeline.py",
        "            return_exceptions=True," + CRLF
        + "        )" + CRLF
        + "        for (hr, _), result in zip(batch, results):",
        "            return_exceptions=False," + CRLF
        + "        )" + CRLF
        + "        for (hr, _), result in zip(batch, results):",
    ),
]
