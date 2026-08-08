"""Поломки для разбора личных сообщений в `backend/flows.py`.

Приём входящего, накопитель отложенного разбора, его гашение и сам разбор
накопленного ответа HR.

Где поломка захватывает конец строки, перевод пишется через `CRLF`: рабочее
дерево здесь с виндовыми переводами, и поиск по `\\n` не находит ничего.
"""

CRLF = "\r\n"

MUTATIONS = [
    # process_dm: письмо от бота перестаёт отсеиваться
    (
        "backend/flows/pipeline.py",
        "    if not msg.from_user or msg.from_user.is_bot:" + CRLF,
        "    if not msg.from_user:" + CRLF,
    ),
    # process_dm: письмо без отправителя перестаёт отсеиваться
    (
        "backend/flows/pipeline.py",
        "    if not msg.from_user or msg.from_user.is_bot:" + CRLF,
        "    if msg.from_user and msg.from_user.is_bot:" + CRLF,
    ),
    # process_dm: незаведённый собеседник перестаёт отсеиваться
    (
        "backend/flows/pipeline.py",
        "    if hr_lookup is None:" + CRLF + "        return" + CRLF,
        "",
    ),
    # process_dm: чёрный список перестаёт глушить входящее
    (
        "backend/flows/pipeline.py",
        "    if bl_value:" + CRLF
        + "        # HR в активном blacklist",
        "    if False:" + CRLF
        + "        # HR в активном blacklist",
    ),
    # process_dm: номер собеседника не дописывается в карточку
    (
        "backend/flows/pipeline.py",
        "            if hr.telegram_user_id is None:" + CRLF
        + "                hr.telegram_user_id = sender_id" + CRLF,
        "",
    ),
    # process_dm: смена имени собеседника не переносится в карточку
    (
        "backend/flows/pipeline.py",
        "            refresh_hr_username(hr, sender_username)" + CRLF,
        "",
    ),
    # process_dm: своя картинка карточки затирается чужой
    (
        "backend/flows/pipeline.py",
        "            if avatar_bytes is not None and hr.avatar is None:",
        "            if avatar_bytes is not None:",
    ),
    # process_dm: аватар тянут и у карточки, где он уже есть
    (
        "backend/flows/pipeline.py",
        "    if client is not None and hr_lookup.avatar is None:",
        "    if client is not None:",
    ),
    # process_dm: ответ перестаёт привязывать письмо к своей вакансии
    (
        "backend/flows/pipeline.py",
        "            if reply_to_id:" + CRLF
        + "                vacancy_id = await resolve_reply_target_vacancy(" + CRLF
        + "                    session, hr.id, reply_to_id," + CRLF
        + "                )" + CRLF,
        "",
    ),
    # process_dm: запасная привязка к свежей вакансии пропадает
    (
        "backend/flows/pipeline.py",
        "            if vacancy_id is None:" + CRLF
        + "                vacancy_id = await find_latest_vacancy_id_for_hr(" + CRLF
        + "                    session, hr.id, as_of=msg.date," + CRLF
        + "                )" + CRLF,
        "",
    ),
    # process_dm: в накопитель уходит текст с цитатой
    (
        "backend/flows/pipeline.py",
        "        schedule_classification(hr.id, vacancy_id, new_msg_id, classify_text)",
        "        schedule_classification(hr.id, vacancy_id, new_msg_id, text)",
    ),
    # process_dm: вакансия вне досягаемости автоматики всё равно разбирается
    (
        "backend/flows/pipeline.py",
        "    if v_status is not None and is_terminal_for_auto(v_status):" + CRLF
        + "        logger.info(" + CRLF
        + '            "vacancy %s: status=%s terminal for auto, skip classification",'
        + CRLF,
        "    if False:" + CRLF
        + "        logger.info(" + CRLF
        + '            "vacancy %s: status=%s terminal for auto, skip classification",'
        + CRLF,
    ),
    # schedule_dm_classification: сообщение без текста всё равно копится
    (
        "backend/flows/pipeline.py",
        "        if not text:" + CRLF
        + "            # Медиа-only без подписи нечем классифицировать",
        "        if False:" + CRLF
        + "            # Медиа-only без подписи нечем классифицировать",
    ),
    # schedule_dm_classification: останавливающийся бот всё равно копит
    (
        "backend/flows/pipeline.py",
        "        if self._shutting_down:" + CRLF
        + "            return" + CRLF
        + "        if not text:" + CRLF,
        "        if not text:" + CRLF,
    ),
    # schedule_dm_classification: очередь перестаёт обрезаться сверху
    (
        "backend/flows/pipeline.py",
        "        if len(buf) > self.DM_CLASSIFY_BUFFER_CAP:",
        "        if False:",
    ),
    # schedule_dm_classification: очередь обрезается с конца, а не с начала
    (
        "backend/flows/pipeline.py",
        "            del buf[: dropped]",
        "            del buf[-dropped:]",
    ),
    # schedule_dm_classification: прежний таймер не гасится новым сообщением
    (
        "backend/flows/pipeline.py",
        "        prev = self._dm_classify_tasks.get(hr_id)" + CRLF
        + "        if prev is not None and not prev.done():" + CRLF
        + "            prev.cancel()" + CRLF,
        "",
    ),
    # update_dm_buffer_text: правка меняет не то сообщение
    (
        "backend/flows/pipeline.py",
        '            if item["msg_id"] == msg_id:',
        "            if True:",
    ),
    # update_dm_buffer_text: правка в пустоту оставляет отсутствие
    (
        "backend/flows/pipeline.py",
        '                item["text"] = new_text or ""',
        '                item["text"] = new_text',
    ),
    # remove_dm_buffer_msg: удаление выбрасывает не то сообщение
    (
        "backend/flows/pipeline.py",
        '            item for item in buf if item["msg_id"] != msg_id',
        '            item for item in buf if item["msg_id"] == msg_id',
    ),
    # remove_dm_buffer_msg: опустевший накопитель остаётся жить
    (
        "backend/flows/pipeline.py",
        "        if not self._dm_classify_buffer[hr_id]:" + CRLF
        + "            self._dm_classify_buffer.pop(hr_id, None)" + CRLF,
        "",
    ),
    # cancel_pending: выключение перестаёт сливать накопленное
    (
        "backend/flows/pipeline.py",
        "        if drain and not self._shutting_down:",
        "        if False:",
    ),
    # cancel_pending: слив идёт и у останавливающегося бота
    (
        "backend/flows/pipeline.py",
        "        if drain and not self._shutting_down:",
        "        if drain:",
    ),
    # cancel_pending: сорвавшийся разбор роняет слив остальных
    (
        "backend/flows/pipeline.py",
        "                    return_exceptions=True," + CRLF
        + "                )" + CRLF
        + "                for hr_id, res in zip(hr_ids, results):",
        "                    return_exceptions=False," + CRLF
        + "                )" + CRLF
        + "                for hr_id, res in zip(hr_ids, results):",
    ),
    # cancel_pending: накопленное не выбрасывается после гашения
    (
        "backend/flows/pipeline.py",
        "        self._dm_classify_buffer.clear()" + CRLF,
        "",
    ),
    # _classify_and_apply_for_hr: чёрный список перестаёт отбрасывать пакет
    (
        "backend/flows/pipeline.py",
        "        if bl_value:" + CRLF
        + "            logger.info(" + CRLF
        + '                "debounced classify: hr %d in blacklist (%s) — drop burst",'
        + CRLF,
        "        if False:" + CRLF
        + "            logger.info(" + CRLF
        + '                "debounced classify: hr %d in blacklist (%s) — drop burst",'
        + CRLF,
    ),
    # _classify_and_apply_for_hr: сообщения склеиваются без границ
    (
        "backend/flows/pipeline.py",
        '        text = "\\n\\n".join(item["text"] for item in buf)',
        '        text = "".join(item["text"] for item in buf)',
    ),
    # _classify_and_apply_for_hr: решение относят к первой вакансии пакета
    (
        "backend/flows/pipeline.py",
        "        last = buf[-1]",
        "        last = buf[0]",
    ),
    # _classify_and_apply_for_hr: вакансия вне досягаемости всё равно разбирается
    (
        "backend/flows/pipeline.py",
        "        if v_status is not None and is_terminal_for_auto(v_status):" + CRLF
        + "            logger.info(" + CRLF
        + '                "vacancy %s: status=%s terminal for auto, "' + CRLF,
        "        if False:" + CRLF
        + "            logger.info(" + CRLF
        + '                "vacancy %s: status=%s terminal for auto, "' + CRLF,
    ),
    # _classify_and_apply_for_hr: пустой вердикт всё равно применяется
    (
        "backend/flows/pipeline.py",
        "        if classification is None:" + CRLF
        + "            logger.info(" + CRLF
        + '                "vacancy %s: classifier returned None for hr %d '
        '(%d msgs in burst)",' + CRLF,
        "        if False:" + CRLF
        + "            logger.info(" + CRLF
        + '                "vacancy %s: classifier returned None for hr %d '
        '(%d msgs in burst)",' + CRLF,
    ),
]
