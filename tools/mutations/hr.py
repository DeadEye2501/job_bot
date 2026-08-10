"""Поломки для `backend/repository/hr_identify.py`, `hr_list.py`, `hr_card.py`
и `merging.py`.

Где поломка захватывает конец строки, перевод пишется через `CRLF`: рабочее
дерево здесь с виндовыми переводами, и поиск по `\\n` не находит ничего.
"""

CRLF = "\r\n"

MUTATIONS = [
    # find_known_hr: запасной путь по нику отключён
    (
        "backend/repository/hr_identify.py",
        "    if telegram_username:" + CRLF,
        "    if False:" + CRLF,
    ),
    # find_known_hr: найденное по идентификатору больше не перевешивает
    (
        "backend/repository/hr_identify.py",
        "    if hr is not None:" + CRLF + "        return hr" + CRLF,
        "    if False:" + CRLF + "        return hr" + CRLF,
    ),
    # find_known_hr: запасной путь сравнивает не с тем полем
    (
        "backend/repository/hr_identify.py",
        "select(HR).where(HR.telegram_username == telegram_username)",
        "select(HR).where(HR.name == telegram_username)",
    ),
    # list_open_hr_chats: открытым считается чат и без нашего письма
    (
        "backend/repository/hr_list.py",
        ".where(Message.hr_id == HR.id, ~Message.is_incoming)",
        ".where(Message.hr_id == HR.id)",
    ),
    # find_latest_vacancy_id_for_hr: недоразобранные перестают отсеиваться
    (
        "backend/repository/hr_identify.py",
        "        .where(Vacancy.hr_id == hr_id, Vacancy.is_parsed.is_(True))" + CRLF
        + "        .order_by(",
        "        .where(Vacancy.hr_id == hr_id)" + CRLF + "        .order_by(",
    ),
    # find_latest_vacancy_id_for_hr: подстановка даты создания пропадает
    (
        "backend/repository/hr_identify.py",
        "            func.coalesce(Vacancy.posted_at, Vacancy.created_at).desc(),",
        "            Vacancy.posted_at.desc(),",
    ),
    # find_latest_vacancy_id_for_hr: отсечка по времени сообщения перевёрнута
    (
        "backend/repository/hr_identify.py",
        "func.coalesce(Vacancy.posted_at, Vacancy.created_at) <= as_of",
        "func.coalesce(Vacancy.posted_at, Vacancy.created_at) >= as_of",
    ),
    # count_recent_outgoing: считаются и письма без вакансии
    (
        "backend/repository/hr_identify.py",
        "        Message.vacancy_id.is_not(None)," + CRLF + "        Message.sent_at >= cutoff," + CRLF,
        "        Message.sent_at >= cutoff," + CRLF,
    ),
    # count_recent_outgoing: окно перестаёт зависеть от довода
    (
        "backend/repository/hr_identify.py",
        "cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)",
        "cutoff = datetime.now(timezone.utc) - timedelta(days=14)",
    ),
    # resolve_reply_target_vacancy: номер процитированного письма не проверяется
    (
        "backend/repository/hr_identify.py",
        "            Message.tg_message_id == reply_to_tg_msg_id," + CRLF,
        "",
    ),
    # refresh_hr_username: пустой ник затирает сохранённый
    (
        "backend/repository/hr_identify.py",
        "if sender_username and hr.telegram_username != sender_username:",
        "if hr.telegram_username != sender_username:",
    ),
    # update_hr_fields: пробельное имя перестаёт стираться
    (
        "backend/repository/hr_card.py",
        "hr.name = (str(name).strip() or None) if name is not None else None",
        "hr.name = str(name) if name is not None else None",
    ),
    # update_hr_fields: правка ника перестаёт разбирать введённое
    (
        "backend/repository/hr_card.py",
        "            None if telegram_username is None else typed_username(telegram_username)",
        "            None if telegram_username is None else str(telegram_username)",
    ),
    # get_hr_detail: последняя компания берётся от старой вакансии
    (
        "backend/repository/hr_card.py",
        "            .order_by(Vacancy.created_at.desc(), Vacancy.id.desc())" + CRLF + "            .limit(1)" + CRLF,
        "            .order_by(Vacancy.created_at.asc(), Vacancy.id.asc())" + CRLF + "            .limit(1)" + CRLF,
    ),
    # get_hr_detail: в счётчик карточки попадает вся переписка
    (
        "backend/repository/hr_card.py",
        "                Message.hr_id == hr_id," + CRLF
        + "                *UNREAD_INCOMING," + CRLF,
        "                Message.hr_id == hr_id," + CRLF,
    ),
    # Отметка чёрного списка уехала в `blacklist_marks`, цели вместе с ней:
    # тремя копиями искалось одно место, и цель у него теперь одна.
    # hr_blacklist_candidates: написание по идентификатору пропадает
    (
        "backend/repository/hr_card.py",
        '        out.append(f"user_id:{hr.telegram_user_id}")',
        "        pass",
    ),
    # hr_blacklist_preferred_value: кнопка пишет номер вместо ника
    (
        "backend/repository/hr_card.py",
        "    return preferred_blacklist_value(hr_blacklist_candidates(hr))" + CRLF,
        "    return hr_blacklist_candidates(hr)[-1]" + CRLF,
    ),
    # list_hr_with_counts: порядок выборщика теряет разрешитель по имени
    (
        "backend/repository/hr_list.py",
        "        base = (" + CRLF
        + '            select(HR, func.count(Vacancy.id).label("cnt"))' + CRLF
        + "            .outerjoin(Vacancy, Vacancy.hr_id == HR.id)" + CRLF
        + "            .group_by(HR.id)" + CRLF
        + "            .order_by(func.count(Vacancy.id).desc(), HR.name.asc())",
        "        base = (" + CRLF
        + '            select(HR, func.count(Vacancy.id).label("cnt"))' + CRLF
        + "            .outerjoin(Vacancy, Vacancy.hr_id == HR.id)" + CRLF
        + "            .group_by(HR.id)" + CRLF
        + "            .order_by(func.count(Vacancy.id).desc())",
    ),
    # list_hr_with_counts: у контактов порядок по давности перевёрнут
    (
        "backend/repository/hr_list.py",
        "                last_act_subq.c.last_act.desc().nullslast(),",
        "                last_act_subq.c.last_act.asc().nullslast(),",
    ),
    # list_hr_with_counts: удалённые сообщения снова считаются перепиской
    (
        "backend/repository/hr_list.py",
        "            .where(Message.is_deleted.is_(False))" + CRLF + "            .group_by(Message.hr_id)" + CRLF,
        "            .group_by(Message.hr_id)" + CRLF,
    ),
    # list_hr_with_counts: поиск перестаёт смотреть в ник
    (
        "backend/repository/hr_list.py",
        "        if matches_search(search, hr.name, hr.telegram_username)",
        "        if matches_search(search, hr.name)",
    ),
    # matches_search: пустой образец начинает отсеивать вместо того, чтобы пропускать
    (
        "backend/repository/search.py",
        "    if not needle:" + CRLF + "        return True" + CRLF,
        "    if not needle:" + CRLF + "        return False" + CRLF,
    ),
    # matches_search: пробелы по краям образца перестают срезаться
    (
        "backend/repository/search.py",
        '    needle = (search or "").strip().casefold()',
        '    needle = (search or "").casefold()',
    ),
    # list_hr_with_counts: страница режется до отбора
    (
        "backend/repository/hr_list.py",
        "        counts = counts[offset : offset + limit]",
        "        counts = counts[offset:offset]",
    ),
    # list_hr_with_counts: последняя компания выбирается по старой вакансии
    (
        "backend/repository/hr_list.py",
        "                    Vacancy.created_at.desc()," + CRLF + "                    Vacancy.id.desc()," + CRLF,
        "                    Vacancy.created_at.asc()," + CRLF + "                    Vacancy.id.asc()," + CRLF,
    ),
    # list_hr_with_counts: в непрочитанные попадает вся переписка
    (
        "backend/repository/hr_list.py",
        "                Message.hr_id.is_not(None)," + CRLF
        + "                *UNREAD_INCOMING," + CRLF,
        "                Message.hr_id.is_not(None)," + CRLF,
    ),
    # delete_hr: переписка переживает удаление человека
    (
        "backend/repository/hr_card.py",
        "        await session.execute(delete(Message).where(Message.hr_id == hr_id))",
        "        await session.execute(select(Message).where(Message.hr_id == hr_id))",
    ),
    # delete_hr: вакансии удаляются вместе с HR вместо отвязки
    (
        "backend/repository/hr_card.py",
        "            update(Vacancy).where(Vacancy.hr_id == hr_id).values(hr_id=None)",
        "            delete(Vacancy).where(Vacancy.hr_id == hr_id)",
    ),
    # load_merge_pair: слияние записи самой с собой проходит
    (
        "backend/repository/merging.py",
        '        raise ValueError(f"{subject}: absorbed_id == survivor_id")',
        "        pass",
    ),
    # merge_hr: наличие учётной записи определяется по нику
    (
        "backend/repository/hr_card.py",
        "survivor_has_tg = survivor.telegram_user_id is not None",
        "survivor_has_tg = survivor.telegram_username is not None",
    ),
    # merge_hr: чужое имя затирает своё
    (
        "backend/repository/hr_card.py",
        "    if not survivor.name and abs_name:",
        "    if abs_name:",
    ),
    # concat_notes: разделитель между заметками пропадает
    (
        "backend/repository/merging.py",
        'return "\\n---\\n".join(parts)',
        'return "".join(parts)',
    ),
    # find_or_create_hr: по нику подхватывается и запись с чужим идентификатором
    (
        "backend/repository/hr_identify.py",
        "                    HR.telegram_user_id.is_(None)," + CRLF,
        "",
    ),
    # find_or_create_hr: аватар затирает уже сохранённый
    (
        "backend/repository/hr_identify.py",
        "if avatar is not None and hr.avatar is None:",
        "if avatar is not None:",
    ),
    # find_or_create_hr: имя из Telegram затирает введённое пользователем
    (
        "backend/repository/hr_identify.py",
        "    if not hr.name and full_name:",
        "    if full_name:",
    ),
]
