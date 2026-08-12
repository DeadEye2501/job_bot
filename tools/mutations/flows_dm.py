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
        "backend/flows/dm.py",
        "if not msg.from_user or msg.from_user.is_bot:" + CRLF,
        "if not msg.from_user:" + CRLF,
    ),
    # process_dm: письмо без отправителя перестаёт отсеиваться
    (
        "backend/flows/dm.py",
        "if not msg.from_user or msg.from_user.is_bot:" + CRLF,
        "if msg.from_user and msg.from_user.is_bot:" + CRLF,
    ),
    # process_dm: незаведённый собеседник перестаёт отсеиваться
    (
        "backend/flows/dm.py",
        "    if hr_lookup is None:" + CRLF + "        return" + CRLF,
        "",
    ),
    # process_dm: чёрный список перестаёт глушить входящее
    (
        "backend/flows/dm.py",
        "    if not blacklisted:" + CRLF + "        return hr" + CRLF,
        "    if True:" + CRLF + "        return hr" + CRLF,
    ),
    # process_dm: номер собеседника не дописывается в карточку
    (
        "backend/flows/dm.py",
        "            if hr.telegram_user_id is None:" + CRLF
        + "                hr.telegram_user_id = sender_id" + CRLF,
        "",
    ),
    # process_dm: смена имени собеседника не переносится в карточку
    (
        "backend/flows/dm.py",
        "            refresh_hr_username(hr, sender_username)" + CRLF,
        "",
    ),
    # process_dm: своя картинка карточки затирается чужой
    (
        "backend/flows/dm.py",
        "        if avatar_bytes is not None and hr.avatar is None:",
        "        if avatar_bytes is not None:",
    ),
    # process_dm: аватар тянут и у карточки, где он уже есть
    (
        "backend/flows/dm.py",
        "if client is not None and hr_lookup.avatar is None:",
        "if client is not None:",
    ),
    # process_dm: ответ перестаёт привязывать письмо к своей вакансии
    (
        "backend/flows/dm.py",
        "    if reply_to_id:" + CRLF
        + "        by_reply = await resolve_reply_target_vacancy(session, hr_id, reply_to_id)" + CRLF
        + "        if by_reply is not None:" + CRLF
        + "            return by_reply" + CRLF,
        "",
    ),
    # process_dm: запасная привязка к свежей вакансии пропадает
    (
        "backend/flows/dm.py",
        "    return await find_latest_vacancy_id_for_hr(session, hr_id, as_of=msg.date)" + CRLF,
        "    return None" + CRLF,
    ),
    # process_dm: в накопитель уходит текст с цитатой
    (
        "backend/flows/dm.py",
        "        schedule_classification(hr_lookup.id, vacancy_id, new_msg_id, classify_text)",
        "        schedule_classification(hr_lookup.id, vacancy_id, new_msg_id, extract_dm_text(msg))",
    ),
    # process_dm: вакансия вне досягаемости автоматики всё равно разбирается
    (
        "backend/flows/dm.py",
        "    if v_status is not None and is_terminal_for_auto(v_status):" + CRLF
        + "        logger.info(" + CRLF
        + '            "vacancy %s: status=%s terminal for auto, skip classification",'
        + CRLF,
        "    if False:" + CRLF
        + "        logger.info(" + CRLF
        + '            "vacancy %s: status=%s terminal for auto, skip classification",'
        + CRLF,
    ),
    # cancel_pending_dm_classifications: начавшийся разбор снова не ждут
    (
        "backend/flows/dm_classify.py",
        "    waited = tasks + [t for t in pipeline._dm_classify_running if not t.done()]",
        "    waited = tasks",
    ),
    # cancel_pending_dm_classifications: переход в OFF снова гасит разбор
    (
        "backend/flows/dm_classify.py",
        "    if drain:" + CRLF + "        return",
        "    if False:" + CRLF + "        return",
    ),
    # cancel_pending_dm_classifications: выключение перестаёт гасить опоздавших
    (
        "backend/flows/dm_classify.py",
        "    for t in pending:" + CRLF + "        t.cancel()",
        "    for t in pending:" + CRLF + "        pass",
    ),
    # _run_debounced_classify: доработавший разбор остаётся в списке ждущих
    (
        "backend/flows/dm_classify.py",
        "        pipeline._dm_classify_running.discard(current)",
        "        pass",
    ),
    # _run_debounced_classify: начавшийся разбор не попадает в список ждущих
    (
        "backend/flows/dm_classify.py",
        "    pipeline._dm_classify_running.add(current)",
        "    pipeline._dm_classify_running.discard(current)",
    ),
    # schedule_dm_classification: сообщение без текста всё равно копится
    (
        "backend/flows/dm_classify.py",
        "    if not text:" + CRLF
        + "        # Медиа-only без подписи нечем классифицировать",
        "    if False:" + CRLF
        + "        # Медиа-only без подписи нечем классифицировать",
    ),
    # schedule_dm_classification: останавливающийся бот всё равно копит
    (
        "backend/flows/dm_classify.py",
        "    if pipeline._shutting_down:" + CRLF
        + "        return" + CRLF
        + "    if not text:" + CRLF,
        "    if not text:" + CRLF,
    ),
    # schedule_dm_classification: очередь перестаёт обрезаться сверху
    (
        "backend/flows/dm_classify.py",
        "    if len(buf) > pipeline.DM_CLASSIFY_BUFFER_CAP:",
        "    if False:",
    ),
    # schedule_dm_classification: очередь обрезается с конца, а не с начала
    (
        "backend/flows/dm_classify.py",
        "        del buf[: dropped]",
        "        del buf[-dropped:]",
    ),
    # schedule_dm_classification: прежний таймер не гасится новым сообщением
    (
        "backend/flows/dm_classify.py",
        "    prev = pipeline._dm_classify_tasks.get(hr_id)" + CRLF
        + "    if prev is not None and not prev.done():" + CRLF
        + "        prev.cancel()" + CRLF,
        "",
    ),
    # update_dm_buffer_text: правка меняет не то сообщение
    (
        "backend/flows/dm_classify.py",
        '        if item["msg_id"] == msg_id:',
        "        if True:",
    ),
    # update_dm_buffer_text: правка в пустоту оставляет отсутствие
    (
        "backend/flows/dm_classify.py",
        '            item["text"] = new_text or ""',
        '            item["text"] = new_text',
    ),
    # remove_dm_buffer_msg: удаление выбрасывает не то сообщение
    (
        "backend/flows/dm_classify.py",
        '        item for item in buf if item["msg_id"] != msg_id',
        '        item for item in buf if item["msg_id"] == msg_id',
    ),
    # remove_dm_buffer_msg: опустевший накопитель остаётся жить
    (
        "backend/flows/dm_classify.py",
        "    if not pipeline._dm_classify_buffer[hr_id]:" + CRLF
        + "        pipeline._dm_classify_buffer.pop(hr_id, None)" + CRLF,
        "",
    ),
    # cancel_pending: выключение перестаёт сливать накопленное
    (
        "backend/flows/dm_classify.py",
        "    if drain and not pipeline._shutting_down:",
        "    if False:",
    ),
    # cancel_pending: слив идёт и у останавливающегося бота
    (
        "backend/flows/dm_classify.py",
        "    if drain and not pipeline._shutting_down:",
        "    if drain:",
    ),
    # cancel_pending: сорвавшийся разбор роняет слив остальных
    (
        "backend/flows/dm_classify.py",
        "                return_exceptions=True," + CRLF
        + "            )" + CRLF
        + "            for hr_id, res in zip(hr_ids, results):",
        "                return_exceptions=False," + CRLF
        + "            )" + CRLF
        + "            for hr_id, res in zip(hr_ids, results):",
    ),
    # cancel_pending: накопленное не выбрасывается после гашения
    (
        "backend/flows/dm_classify.py",
        "    pipeline._dm_classify_buffer.clear()" + CRLF,
        "",
    ),
    # classify_and_apply_for_hr: чёрный список перестаёт отбрасывать пакет
    (
        "backend/flows/dm_classify.py",
        "    if bl_value:" + CRLF
        + "        logger.info(" + CRLF
        + '            "debounced classify: hr %d in blacklist (%s) — drop burst",'     + CRLF,
        "    if False:" + CRLF
        + "        logger.info(" + CRLF
        + '            "debounced classify: hr %d in blacklist (%s) — drop burst",'     + CRLF,
    ),
    # classify_and_apply_for_hr: сообщения склеиваются без границ
    (
        "backend/flows/dm_classify.py",
        '    text = "\\n\\n".join(item["text"] for item in buf)',
        '    text = "".join(item["text"] for item in buf)',
    ),
    # classify_and_apply_for_hr: решение относят к первой вакансии пакета
    (
        "backend/flows/dm_classify.py",
        "    last = buf[-1]",
        "    last = buf[0]",
    ),
    # classify_and_apply_for_hr: вакансия вне досягаемости всё равно разбирается
    (
        "backend/flows/dm_classify.py",
        "    if v_status is not None and is_terminal_for_auto(v_status):" + CRLF
        + "        logger.info(" + CRLF
        + '            "vacancy %s: status=%s terminal for auto, "' + CRLF,
        "    if False:" + CRLF
        + "        logger.info(" + CRLF
        + '            "vacancy %s: status=%s terminal for auto, "' + CRLF,
    ),
    # classify_and_apply_for_hr: пустой вердикт всё равно применяется
    (
        "backend/flows/dm_classify.py",
        "    if classification is None:" + CRLF
        + "        logger.info(" + CRLF
        + '            "vacancy %s: classifier returned None for hr %d '     '(%d msgs in burst)",' + CRLF,
        "    if False:" + CRLF
        + "        logger.info(" + CRLF
        + '            "vacancy %s: classifier returned None for hr %d '     '(%d msgs in burst)",' + CRLF,
    ),
]
