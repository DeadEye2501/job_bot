"""Поломки для работы с вакансией в `backend/flows.py`.

Приём объявления, заведение и удаление строки, кэш векторов, разбор, приговор
и отправка отклика.

Где поломка захватывает конец строки, перевод пишется через `CRLF`: рабочее
дерево здесь с виндовыми переводами, и поиск по `\\n` не находит ничего.
"""

CRLF = "\r\n"

MUTATIONS = [
    # _ingest_post: служебная запись и опрос доходят до разбора
    (
        "backend/flows/ingest.py",
        "    if not text or msg.service is not None or msg.poll is not None:" + CRLF
        + "        return" + CRLF,
        "    if not text:" + CRLF + "        return" + CRLF,
    ),
    # _ingest_post: объявление без текста доходит до разбора
    (
        "backend/flows/ingest.py",
        "    if not text or msg.service is not None or msg.poll is not None:",
        "    if msg.service is not None or msg.poll is not None:",
    ),
    # _ingest_post: перепост заводит вторую вакансию
    (
        "backend/flows/ingest.py",
        "    if similar_id is not None:" + CRLF
        + "        # Could be a real duplicate",
        "    if False:" + CRLF + "        # Could be a real duplicate",
    ),
    # _ingest_post: недоразобранный повтор не дописывается
    (
        "backend/flows/ingest.py",
        "        unparsed = await pipeline._is_unparsed_vacancy(similar_id)" + CRLF
        + "        if unparsed:",
        "        unparsed = await pipeline._is_unparsed_vacancy(similar_id)" + CRLF
        + "        if False:",
    ),
    # _ingest_post: незаведённая строка всё равно идёт в разбор
    (
        "backend/flows/ingest.py",
        "    if new_vacancy_id is not None:" + CRLF
        + "        await pipeline._parse_and_update_vacancy(" + CRLF,
        "    if True:" + CRLF
        + "        await pipeline._parse_and_update_vacancy(" + CRLF,
    ),
    # _save_new_vacancy: вектор не попадает в кэш
    (
        "backend/flows/ingest.py",
        "            embeddings._append_embedding(pipeline, new_vacancy.id, embedding)" + CRLF,
        "",
    ),
    # _save_new_vacancy: повторное заведение выдаётся за успех
    (
        "backend/flows/ingest.py",
        '                msg.id,' + CRLF
        + "            )" + CRLF
        + "            return None" + CRLF,
        '                msg.id,' + CRLF
        + "            )" + CRLF
        + "            return 0" + CRLF,
    ),
    # _ensure_embedding_cache: кэш перечитывается на каждом обходе
    (
        "backend/flows/embeddings.py",
        "    if pipeline._embedding_cache_loaded:" + CRLF + "        return" + CRLF,
        "",
    ),
    # _ensure_embedding_cache: вакансии без вектора попадают в кэш
    (
        "backend/flows/embeddings.py",
        "                select(Vacancy.id, Vacancy.embedding).where(" + CRLF
        + "                    Vacancy.embedding.is_not(None)" + CRLF
        + "                )" + CRLF,
        "                select(Vacancy.id, Vacancy.embedding)" + CRLF,
    ),
    # _drop_embedding: вычёркивание отсутствующего рушит кэш
    (
        "backend/flows/embeddings.py",
        "    if idx.size == 0:" + CRLF + "        return" + CRLF,
        "",
    ),
    # _delete_vacancy: вектор удалённой вакансии остаётся в кэше
    (
        "backend/flows/cleanup.py",
        "    embeddings._drop_embedding(pipeline, vacancy_id)" + CRLF
        + '    logger.info("vacancy %d: deleted from DB and embedding cache", vacancy_id)'     + CRLF,
        '    logger.info("vacancy %d: deleted from DB and embedding cache", vacancy_id)'     + CRLF,
    ),
    # _delete_vacancy_as_trash: отметка о мусоре не пишется
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
    # _parse_and_update_vacancy: пустышка доходит до проверяльщика
    (
        "backend/flows/pipeline.py",
        "        if is_empty_vacancy(parsed):",
        "        if False:",
    ),
    # _parse_and_update_vacancy: пустышку удаляют и при повторном прогоне
    (
        "backend/flows/pipeline.py",
        "        if is_empty_vacancy(parsed):" + CRLF
        + "            if allow_delete:",
        "        if is_empty_vacancy(parsed):" + CRLF + "            if True:",
    ),
    # _parse_and_update_vacancy: чёрный список читает обрезанный текст
    (
        "backend/flows/pipeline.py",
        "        blacklist_match = check_blacklist(text, self._blacklist_patterns)",
        "        blacklist_match = check_blacklist(text[:100], self._blacklist_patterns)",
    ),
    # _parse_and_update_vacancy: проверяльщика зовут и для отсеянного
    (
        "backend/flows/pipeline.py",
        "        if status == VacancyStatus.NEW:" + CRLF
        + "            validation = await validate_vacancy_fit(",
        "        if True:" + CRLF
        + "            validation = await validate_vacancy_fit(",
    ),
    # _parse_and_update_vacancy: молчание проверяльщика читается как согласие
    (
        "backend/flows/pipeline.py",
        "            if validation is None:" + CRLF
        + "                status = VacancyStatus.NOT_FIT" + CRLF,
        "            if False:" + CRLF
        + "                status = VacancyStatus.NOT_FIT" + CRLF,
    ),
    # _parse_and_update_vacancy: мусор удаляют и при повторном прогоне
    (
        "backend/flows/pipeline.py",
        '            elif validation.verdict == "trash":' + CRLF
        + "                if allow_delete:",
        '            elif validation.verdict == "trash":' + CRLF
        + "                if True:",
    ),
    # _parse_and_update_vacancy: отказ проверяльщика ни к чему не ведёт
    (
        "backend/flows/pipeline.py",
        '            elif validation.verdict == "reject":' + CRLF
        + "                status = VacancyStatus.NOT_FIT" + CRLF,
        '            elif False:' + CRLF
        + "                status = VacancyStatus.NOT_FIT" + CRLF,
    ),
    # _parse_and_update_vacancy: признак разбора не ставится
    (
        "backend/flows/pipeline.py",
        "                v.is_parsed = True" + CRLF + CRLF + "                v.title",
        "                v.title",
    ),
    # _parse_and_update_vacancy: пустой повторный разбор затирает стек
    (
        "backend/flows/pipeline.py",
        "                if parsed.stack:" + CRLF
        + "                    v.stack = parsed.stack" + CRLF
        + "                    v.score = score" + CRLF
        + "                else:" + CRLF
        + "                    v.stack = v.stack or []" + CRLF,
        "                if True:" + CRLF
        + "                    v.stack = parsed.stack" + CRLF
        + "                    v.score = score" + CRLF
        + "                else:" + CRLF
        + "                    v.stack = v.stack or []" + CRLF,
    ),
    # _parse_and_update_vacancy: компания не привязывается
    (
        "backend/flows/pipeline.py",
        "                    if company is not None:" + CRLF
        + "                        v.company_id = company.id" + CRLF,
        "",
    ),
    # _parse_and_update_vacancy: HR не привязывается
    (
        "backend/flows/pipeline.py",
        "                    v.hr_id = hr.id" + CRLF
        + "                    # Захватываем до выхода из сессии",
        "                    # Захватываем до выхода из сессии",
    ),
    # _parse_and_update_vacancy: отклик уходит и у непригодной вакансии
    (
        "backend/flows/pipeline.py",
        "            status == VacancyStatus.NEW" + CRLF
        + "            and hr_for_send is not None" + CRLF
        + "            and self._rs.auto_apply" + CRLF,
        "            hr_for_send is not None" + CRLF
        + "            and self._rs.auto_apply" + CRLF,
    ),
    # _parse_and_update_vacancy: выключенная автоотправка всё равно шлёт
    (
        "backend/flows/pipeline.py",
        "            status == VacancyStatus.NEW" + CRLF
        + "            and hr_for_send is not None" + CRLF
        + "            and self._rs.auto_apply" + CRLF,
        "            status == VacancyStatus.NEW" + CRLF
        + "            and hr_for_send is not None" + CRLF,
    ),
    # _parse_and_update_vacancy: попытка отправки не записывается в ленту
    (
        "backend/flows/pipeline.py",
        "                            kind=\"auto_send\"," + CRLF
        + '                            payload={"ok": ok, "reason": reason},' + CRLF,
        "                            kind=\"auto_send\"," + CRLF
        + '                            payload={"ok": True, "reason": "sent"},' + CRLF,
    ),
    # _save_empty_vacancy: признак разбора не ставится
    (
        "backend/flows/pipeline.py",
        "                v.is_parsed = True" + CRLF
        + "                company_dedup_decision",
        "                company_dedup_decision",
    ),
    # _save_empty_vacancy: прежний разбор не стирается
    (
        "backend/flows/pipeline.py",
        "                else:" + CRLF
        + "                    v.title = None" + CRLF
        + "                    v.description = None" + CRLF,
        "                elif False:" + CRLF
        + "                    v.title = None" + CRLF
        + "                    v.description = None" + CRLF,
    ),
    # _send_application: короткая приписка не заменяет полное письмо
    (
        "backend/flows/pipeline.py",
        "        if prior_count == 0:",
        "        if True:",
    ),
    # _send_application: полное письмо шлётся и на второй вакансии
    (
        "backend/flows/pipeline.py",
        "        if prior_count == 0:",
        "        if prior_count >= 0:",
    ),
    # _send_application: пустая анкета отправку не останавливает
    (
        "backend/flows/pipeline.py",
        "            if not self._profile_block:" + CRLF
        + "                logger.warning(" + CRLF
        + '                    "vacancy %d: profile_block empty, skipping send",' + CRLF,
        "            if False:" + CRLF
        + "                logger.warning(" + CRLF
        + '                    "vacancy %d: profile_block empty, skipping send",' + CRLF,
    ),
    # _send_application: отсутствие резюме отправку не останавливает
    (
        "backend/flows/pipeline.py",
        "            if cv_path is None or not cv_path.is_file():",
        "            if False:",
    ),
    # _send_application: защита от повторной отправки снимается
    (
        "backend/flows/pipeline.py",
        "            if not force and v.status == VacancyStatus.APPLIED:",
        "            if False:",
    ),
    # _send_application: решение пользователя защиту не перебивает
    (
        "backend/flows/pipeline.py",
        "            if not force and v.status == VacancyStatus.APPLIED:",
        "            if v.status == VacancyStatus.APPLIED:",
    ),
    # _try_auto_send: окно запрета частоты перестаёт держать автоотправку
    (
        "backend/flows/pipeline.py",
        "            if remaining > 0:",
        "            if False:",
    ),
    # send_application_for_vacancy: вакансия без HR всё равно идёт в отправку
    (
        "backend/flows/pipeline.py",
        "            if v.hr is None:" + CRLF
        + "                logger.warning(" + CRLF
        + '                    "send_application: vacancy %d has no HR linked", vacancy_id'
        + CRLF,
        "            if False:" + CRLF
        + "                logger.warning(" + CRLF
        + '                    "send_application: vacancy %d has no HR linked", vacancy_id'
        + CRLF,
    ),
    # send_application_for_vacancy: повторное нажатие не отбивается
    (
        "backend/flows/pipeline.py",
        "            if v.status == VacancyStatus.APPLIED:" + CRLF
        + "                logger.info(" + CRLF
        + '                    "send_application: vacancy %d already APPLIED, refusing re-send",'
        + CRLF,
        "            if False:" + CRLF
        + "                logger.info(" + CRLF
        + '                    "send_application: vacancy %d already APPLIED, refusing re-send",'
        + CRLF,
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
    # _spawn_hr_backfill: законченный догон из списка не убирается
    (
        "backend/flows/pipeline.py",
        "        task.add_done_callback(self._backfill_tasks.discard)",
        "        pass",
    ),
    # mark_shutting_down: незаконченный догон не гасится
    (
        "backend/flows/pipeline.py",
        "        for task in self._backfill_tasks:" + CRLF
        + "            task.cancel()" + CRLF,
        "",
    ),
]
