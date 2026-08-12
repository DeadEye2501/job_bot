"""Поломки для работы с вакансией в `backend/flows.py`.

Приём объявления, заведение и удаление строки, кэш векторов, разбор, приговор
и отправка отклика.

Где поломка захватывает конец строки, перевод пишется через `CRLF`: рабочее
дерево здесь с виндовыми переводами, и поиск по `\\n` не находит ничего.
"""

CRLF = "\r\n"

MUTATIONS = [
    # ingest_post: служебная запись и опрос доходят до разбора
    (
        "backend/flows/ingest.py",
        "    if not text or msg.service is not None or msg.poll is not None:" + CRLF
        + "        return" + CRLF,
        "    if not text:" + CRLF + "        return" + CRLF,
    ),
    # ingest_post: объявление без текста доходит до разбора
    (
        "backend/flows/ingest.py",
        "    if not text or msg.service is not None or msg.poll is not None:",
        "    if msg.service is not None or msg.poll is not None:",
    ),
    # ingest_post: перепост заводит вторую вакансию
    (
        "backend/flows/ingest.py",
        "    if similar_id is not None:" + CRLF
        + "        # Could be a real duplicate",
        "    if False:" + CRLF + "        # Could be a real duplicate",
    ),
    # ingest_post: недоразобранный повтор не дописывается
    (
        "backend/flows/ingest.py",
        "        unparsed = await parse.is_unparsed_vacancy(pipeline, similar_id)" + CRLF
        + "        if unparsed:",
        "        unparsed = await parse.is_unparsed_vacancy(pipeline, similar_id)" + CRLF
        + "        if False:",
    ),
    # ingest_post: незаведённая строка всё равно идёт в разбор
    (
        "backend/flows/ingest.py",
        "    if new_vacancy_id is not None:" + CRLF
        + "        await parse.parse_and_update_vacancy(pipeline, " + CRLF,
        "    if True:" + CRLF
        + "        await parse.parse_and_update_vacancy(pipeline, " + CRLF,
    ),
    # save_new_vacancy: вектор не попадает в кэш
    (
        "backend/flows/ingest.py",
        "            embeddings.append_embedding(pipeline, new_vacancy.id, embedding)" + CRLF,
        "",
    ),
    # save_new_vacancy: повторное заведение выдаётся за успех
    (
        "backend/flows/ingest.py",
        '                post.msg.id,' + CRLF
        + "            )" + CRLF
        + "            return None" + CRLF,
        '                post.msg.id,' + CRLF
        + "            )" + CRLF
        + "            return 0" + CRLF,
    ),
    # ensure_embedding_cache: кэш перечитывается на каждом обходе
    (
        "backend/flows/embeddings.py",
        "    if pipeline._embedding_cache_loaded:" + CRLF + "        return" + CRLF,
        "",
    ),
    # ensure_embedding_cache: вакансии без вектора попадают в кэш
    (
        "backend/flows/embeddings.py",
        "                select(Vacancy.id, Vacancy.embedding).where(" + CRLF
        + "                    Vacancy.embedding.is_not(None)" + CRLF
        + "                )" + CRLF,
        "                select(Vacancy.id, Vacancy.embedding)" + CRLF,
    ),
    # drop_embedding: вычёркивание отсутствующего рушит кэш
    (
        "backend/flows/embeddings.py",
        "    if idx.size == 0:" + CRLF + "        return" + CRLF,
        "",
    ),
    # delete_vacancy: вектор удалённой вакансии остаётся в кэше
    (
        "backend/flows/cleanup.py",
        "    embeddings.drop_embedding(pipeline, vacancy_id)" + CRLF
        + '    logger.info("vacancy %d: deleted from DB and embedding cache", vacancy_id)'     + CRLF,
        '    logger.info("vacancy %d: deleted from DB and embedding cache", vacancy_id)'     + CRLF,
    ),
    # delete_vacancy_as_trash: отметка о мусоре не пишется
    (
        "backend/flows/cleanup.py",
        "        await record_trash_event(" + CRLF
        + "            session," + CRLF
        + "            source_channel_id=channel_id," + CRLF
        + "            source_msg_id=msg_id," + CRLF
        + "            reason=reason," + CRLF
        + "        )" + CRLF,
        "",
    ),
    # parse_and_update_vacancy: пустышка доходит до проверяльщика
    (
        "backend/flows/parse.py",
        "    if is_empty_vacancy(parsed):",
        "    if False:",
    ),
    # parse_and_update_vacancy: пустышку удаляют и при повторном прогоне
    (
        "backend/flows/parse.py",
        "    if is_empty_vacancy(parsed):" + CRLF
        + "        if allow_delete:",
        "    if is_empty_vacancy(parsed):" + CRLF + "        if True:",
    ),
    # parse_and_update_vacancy: чёрный список читает обрезанный текст
    (
        "backend/flows/parse.py",
        "    blacklist_match = check_blacklist(text, pipeline._blacklist_patterns)",
        "    blacklist_match = check_blacklist(text[:100], pipeline._blacklist_patterns)",
    ),
    # parse_and_update_vacancy: проверяльщика зовут и для отсеянного
    (
        "backend/flows/parse.py",
        "    if status == VacancyStatus.NEW:" + CRLF
        + "        validation = await validate_vacancy_fit(",
        "    if True:" + CRLF
        + "        validation = await validate_vacancy_fit(",
    ),
    # parse_and_update_vacancy: молчание проверяльщика читается как согласие
    (
        "backend/flows/parse.py",
        "        if validation is None:" + CRLF
        + "            status = VacancyStatus.NOT_FIT" + CRLF,
        "        if False:" + CRLF
        + "            status = VacancyStatus.NOT_FIT" + CRLF,
    ),
    # parse_and_update_vacancy: мусор удаляют и при повторном прогоне
    (
        "backend/flows/parse.py",
        '        elif validation.verdict == "trash":' + CRLF
        + "            if allow_delete:",
        '        elif validation.verdict == "trash":' + CRLF
        + "            if True:",
    ),
    # parse_and_update_vacancy: отказ проверяльщика ни к чему не ведёт
    (
        "backend/flows/parse.py",
        '        elif validation.verdict == "reject":' + CRLF
        + "            status = VacancyStatus.NOT_FIT" + CRLF,
        '        elif False:' + CRLF
        + "            status = VacancyStatus.NOT_FIT" + CRLF,
    ),
    # _write_parsed_row: признак разбора не ставится
    (
        "backend/flows/parse.py",
        "    v.is_parsed = True" + CRLF
        + "    _apply_parsed_fields(v, parsed, outcome)",
        "    _apply_parsed_fields(v, parsed, outcome)",
    ),
    # _apply_parsed_fields: пустой повторный разбор затирает стек
    (
        "backend/flows/parse.py",
        "    if parsed.stack or not outcome.keep_previous_stack:" + CRLF
        + "        v.stack = parsed.stack" + CRLF,
        "    if True:" + CRLF + "        v.stack = parsed.stack" + CRLF,
    ),
    # _link_company: компания не привязывается
    (
        "backend/flows/parse.py",
        "    if company is not None:" + CRLF
        + "        v.company_id = company.id" + CRLF,
        "",
    ),
    # _link_resolved_hr: HR не привязывается
    (
        "backend/flows/parse.py",
        "    v.hr_id = hr.id" + CRLF,
        "",
    ),
    # parse_and_update_vacancy: отклик уходит и у непригодной вакансии
    (
        "backend/flows/parse.py",
        "        status == VacancyStatus.NEW" + CRLF
        + "        and hr_for_send is not None" + CRLF
        + "        and pipeline._rs.auto_apply" + CRLF,
        "        hr_for_send is not None" + CRLF
        + "        and pipeline._rs.auto_apply" + CRLF,
    ),
    # parse_and_update_vacancy: выключенная автоотправка всё равно шлёт
    (
        "backend/flows/parse.py",
        "        status == VacancyStatus.NEW" + CRLF
        + "        and hr_for_send is not None" + CRLF
        + "        and pipeline._rs.auto_apply" + CRLF,
        "        status == VacancyStatus.NEW" + CRLF
        + "        and hr_for_send is not None" + CRLF,
    ),
    # parse_and_update_vacancy: попытка отправки не записывается в ленту
    (
        "backend/flows/parse.py",
        "                        kind=\"auto_send\"," + CRLF
        + '                        payload={"ok": ok, "reason": reason},' + CRLF,
        "                        kind=\"auto_send\"," + CRLF
        + '                        payload={"ok": True, "reason": "sent"},' + CRLF,
    ),
    # Поломки «поле пропало из ленты» здесь больше нет, и завести её нечем:
    # заходом Г этапа 4 три перечня прямых полей сведены в
    # `_DIRECT_PARSED_FIELDS`, и вынутое оттуда имя пропадает разом из
    # стирания, записи и ленты. Такая поломка красит половину набора и
    # проверяет не то, ради чего заводилась, — «забыли поле в одном из трёх
    # перечней». Забыть его теперь негде.
    # save_empty_vacancy: пустой разбор щадит прежний стек наравне с обычным
    (
        "backend/flows/parse.py",
        "            keep_previous_stack=False," + CRLF,
        "            keep_previous_stack=True," + CRLF,
    ),
    # save_empty_vacancy: догон переписки заводят и по знакомому HR
    (
        "backend/flows/parse.py",
        "    if hr_created:" + CRLF
        + "        dm_backfill.spawn_hr_backfill(pipeline, hr)" + CRLF,
        "    if hr is not None:" + CRLF
        + "        dm_backfill.spawn_hr_backfill(pipeline, hr)" + CRLF,
    ),
    # save_empty_vacancy: догон переписки не заводят вовсе
    (
        "backend/flows/parse.py",
        "    if hr_created:" + CRLF
        + "        dm_backfill.spawn_hr_backfill(pipeline, hr)" + CRLF,
        "",
    ),
    # _apply_parsed_fields: прежний разбор не стирается
    (
        "backend/flows/parse.py",
        "        _clear_parsed_fields(v, outcome.score)" + CRLF
        + "        return" + CRLF,
        "        return" + CRLF,
    ),
    # send_application: короткая приписка не заменяет полное письмо
    (
        "backend/flows/apply.py",
        "    if prior_count == 0:",
        "    if True:",
    ),
    # send_application: полное письмо шлётся и на второй вакансии
    (
        "backend/flows/apply.py",
        "    if prior_count == 0:",
        "    if prior_count >= 0:",
    ),
    # send_application: пустая анкета отправку не останавливает
    (
        "backend/flows/apply.py",
        "        if not pipeline._profile_block:" + CRLF
        + "            logger.warning(" + CRLF
        + '                "vacancy %d: profile_block empty, skipping send",' + CRLF,
        "        if False:" + CRLF
        + "            logger.warning(" + CRLF
        + '                "vacancy %d: profile_block empty, skipping send",' + CRLF,
    ),
    # send_application: отсутствие резюме отправку не останавливает
    (
        "backend/flows/apply.py",
        "        if cv_path is None or not cv_path.is_file():",
        "        if False:",
    ),
    # send_application: защита от повторной отправки снимается
    (
        "backend/flows/apply.py",
        "        if not force and v.status == VacancyStatus.APPLIED:",
        "        if False:",
    ),
    # send_application: решение пользователя защиту не перебивает
    (
        "backend/flows/apply.py",
        "        if not force and v.status == VacancyStatus.APPLIED:",
        "        if v.status == VacancyStatus.APPLIED:",
    ),
    # try_auto_send: окно запрета частоты перестаёт держать автоотправку
    (
        "backend/flows/apply.py",
        "        if remaining > 0:",
        "        if False:",
    ),
    # send_application_for_vacancy: вакансия без HR всё равно идёт в отправку
    (
        "backend/flows/apply.py",
        "        if v.hr is None:" + CRLF
        + "            logger.warning(" + CRLF
        + '                "send_application: vacancy %d has no HR linked", vacancy_id'     + CRLF,
        "        if False:" + CRLF
        + "            logger.warning(" + CRLF
        + '                "send_application: vacancy %d has no HR linked", vacancy_id'     + CRLF,
    ),
    # send_application_for_vacancy: повторное нажатие не отбивается
    (
        "backend/flows/apply.py",
        "        if v.status == VacancyStatus.APPLIED:" + CRLF
        + "            logger.info(" + CRLF
        + '                "send_application: vacancy %d already APPLIED, refusing re-send",'     + CRLF,
        "        if False:" + CRLF
        + "            logger.info(" + CRLF
        + '                "send_application: vacancy %d already APPLIED, refusing re-send",'     + CRLF,
    ),
    # recover_orphan_vacancies: разобранные вакансии подбираются заново
    (
        "backend/flows/rerun.py",
        "                    Vacancy.is_parsed.is_(False)," + CRLF
        + "                    Vacancy.raw_text.is_not(None)," + CRLF,
        "                    Vacancy.raw_text.is_not(None)," + CRLF,
    ),
    # recover_orphan_vacancies: удаление при подборе запрещается
    (
        "backend/flows/rerun.py",
        "                r.id, text, r.username or \"\", allow_delete=True",
        "                r.id, text, r.username or \"\", allow_delete=False",
    ),
    # spawn_hr_backfill: законченный догон из списка не убирается
    (
        "backend/flows/dm_backfill.py",
        "    task.add_done_callback(pipeline._backfill_tasks.discard)",
        "    pass",
    ),
    # mark_shutting_down: незаконченный догон не гасится
    (
        "backend/flows/pipeline.py",
        "        for task in self._backfill_tasks:" + CRLF
        + "            task.cancel()" + CRLF,
        "",
    ),
]
