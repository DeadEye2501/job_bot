"""Поломки для той части `backend/repository.py`, что отвечает за HR.

Где поломка захватывает конец строки, перевод пишется через `CRLF`: рабочее
дерево здесь с виндовыми переводами, и поиск по `\\n` не находит ничего.
"""

CRLF = "\r\n"

MUTATIONS = [
    # find_known_hr: запасной путь по нику отключён
    (
        "backend/repository.py",
        "    if telegram_username:" + CRLF,
        "    if False:" + CRLF,
    ),
    # find_known_hr: найденное по идентификатору больше не перевешивает
    (
        "backend/repository.py",
        "    if hr is not None:" + CRLF + "        return hr" + CRLF,
        "    if False:" + CRLF + "        return hr" + CRLF,
    ),
    # find_known_hr: запасной путь сравнивает не с тем полем
    (
        "backend/repository.py",
        "select(HR).where(HR.telegram_username == telegram_username)",
        "select(HR).where(HR.name == telegram_username)",
    ),
    # list_open_hr_chats: открытым считается чат и без нашего письма
    (
        "backend/repository.py",
        ".where(Message.hr_id == HR.id, ~Message.is_incoming)",
        ".where(Message.hr_id == HR.id)",
    ),
    # find_latest_vacancy_id_for_hr: недоразобранные перестают отсеиваться
    (
        "backend/repository.py",
        "        .where(Vacancy.hr_id == hr_id, Vacancy.is_parsed.is_(True))",
        "        .where(Vacancy.hr_id == hr_id)",
    ),
    # find_latest_vacancy_id_for_hr: подстановка даты создания пропадает
    (
        "backend/repository.py",
        "            func.coalesce(Vacancy.posted_at, Vacancy.created_at).desc(),",
        "            Vacancy.posted_at.desc(),",
    ),
    # find_latest_vacancy_id_for_hr: отсечка по времени сообщения перевёрнута
    (
        "backend/repository.py",
        "func.coalesce(Vacancy.posted_at, Vacancy.created_at) <= as_of",
        "func.coalesce(Vacancy.posted_at, Vacancy.created_at) >= as_of",
    ),
    # count_recent_outgoing: считаются и письма без вакансии
    (
        "backend/repository.py",
        "        Message.vacancy_id.is_not(None)," + CRLF + "        Message.sent_at >= cutoff," + CRLF,
        "        Message.sent_at >= cutoff," + CRLF,
    ),
    # count_recent_outgoing: окно перестаёт зависеть от довода
    (
        "backend/repository.py",
        "cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)",
        "cutoff = datetime.now(timezone.utc) - timedelta(days=14)",
    ),
    # resolve_reply_target_vacancy: номер процитированного письма не проверяется
    (
        "backend/repository.py",
        "            Message.tg_message_id == reply_to_tg_msg_id," + CRLF,
        "",
    ),
    # refresh_hr_username: пустой ник затирает сохранённый
    (
        "backend/repository.py",
        "if sender_username and hr.telegram_username != sender_username:",
        "if hr.telegram_username != sender_username:",
    ),
    # update_hr_fields: пробельное имя перестаёт стираться
    (
        "backend/repository.py",
        "hr.name = (str(name).strip() or None) if name is not None else None",
        "hr.name = str(name) if name is not None else None",
    ),
    # update_hr_fields: собачка в нике не срезается
    (
        "backend/repository.py",
        "                cleaned = cleaned[1:].strip()",
        "                cleaned = cleaned.strip()",
    ),
    # get_hr_detail: последняя компания берётся от старой вакансии
    (
        "backend/repository.py",
        "            .order_by(Vacancy.created_at.desc(), Vacancy.id.desc())" + CRLF + "            .limit(1)" + CRLF,
        "            .order_by(Vacancy.created_at.asc(), Vacancy.id.asc())" + CRLF + "            .limit(1)" + CRLF,
    ),
    # get_hr_detail: непрочитанными считаются и удалённые
    (
        "backend/repository.py",
        "                Message.read_at.is_(None)," + CRLF + "                Message.is_deleted.is_(False)," + CRLF,
        "                Message.read_at.is_(None)," + CRLF,
    ),
    # _hr_blacklist_value: выключенные записи снова видны
    (
        "backend/repository.py",
        "                Blacklist.active.is_(True)," + CRLF + "            )" + CRLF + "            .order_by(Blacklist.id.asc())",
        "            )" + CRLF + "            .order_by(Blacklist.id.asc())",
    ),
    # _hr_blacklist_value: при двух написаниях побеждает заведённое позже
    (
        "backend/repository.py",
        ".order_by(Blacklist.id.asc())",
        ".order_by(Blacklist.id.desc())",
    ),
    # hr_blacklist_candidates: написание по идентификатору пропадает
    (
        "backend/repository.py",
        '        out.append(f"user_id:{hr.telegram_user_id}")',
        "        pass",
    ),
    # hr_blacklist_preferred_value: кнопка пишет номер вместо ника
    (
        "backend/repository.py",
        '    if hr.telegram_username:' + CRLF + '        return f"@{hr.telegram_username}"' + CRLF,
        "    if False:" + CRLF + '        return f"@{hr.telegram_username}"' + CRLF,
    ),
    # list_hr_with_counts: порядок выборщика теряет разрешитель по имени
    (
        "backend/repository.py",
        ".order_by(func.count(Vacancy.id).desc(), HR.name.asc())",
        ".order_by(func.count(Vacancy.id).desc())",
    ),
    # list_hr_with_counts: у контактов порядок по давности перевёрнут
    (
        "backend/repository.py",
        "                last_act_subq.c.last_act.desc().nullslast(),",
        "                last_act_subq.c.last_act.asc().nullslast(),",
    ),
    # list_hr_with_counts: удалённые сообщения снова считаются перепиской
    (
        "backend/repository.py",
        "            .where(Message.is_deleted.is_(False))" + CRLF + "            .group_by(Message.hr_id)" + CRLF,
        "            .group_by(Message.hr_id)" + CRLF,
    ),
    # list_hr_with_counts: поиск перестаёт смотреть в ник
    (
        "backend/repository.py",
        '                or q in (hr.telegram_username or "").casefold()' + CRLF,
        "",
    ),
    # list_hr_with_counts: страница режется до отбора
    (
        "backend/repository.py",
        "        counts = counts[offset : offset + limit]",
        "        counts = counts[offset:offset]",
    ),
    # list_hr_with_counts: последняя компания выбирается по старой вакансии
    (
        "backend/repository.py",
        "                    Vacancy.created_at.desc()," + CRLF + "                    Vacancy.id.desc()," + CRLF,
        "                    Vacancy.created_at.asc()," + CRLF + "                    Vacancy.id.asc()," + CRLF,
    ),
    # list_hr_with_counts: в непрочитанные попадают и исходящие
    (
        "backend/repository.py",
        "                Message.is_incoming," + CRLF + "                Message.read_at.is_(None)," + CRLF,
        "                Message.read_at.is_(None)," + CRLF,
    ),
    # delete_hr: переписка переживает удаление человека
    (
        "backend/repository.py",
        "        await session.execute(delete(Message).where(Message.hr_id == hr_id))",
        "        await session.execute(select(Message).where(Message.hr_id == hr_id))",
    ),
    # delete_hr: вакансии удаляются вместе с HR вместо отвязки
    (
        "backend/repository.py",
        "            update(Vacancy).where(Vacancy.hr_id == hr_id).values(hr_id=None)",
        "            delete(Vacancy).where(Vacancy.hr_id == hr_id)",
    ),
    # merge_hr: слияние записи самой с собой проходит
    (
        "backend/repository.py",
        '        raise ValueError("merge_hr: absorbed_id == survivor_id")',
        "        return None",
    ),
    # merge_hr: наличие учётной записи определяется по нику
    (
        "backend/repository.py",
        "survivor_has_tg = survivor.telegram_user_id is not None",
        "survivor_has_tg = survivor.telegram_username is not None",
    ),
    # merge_hr: чужое имя затирает своё
    (
        "backend/repository.py",
        "    if not survivor.name and abs_name:",
        "    if abs_name:",
    ),
    # _concat_notes: разделитель между заметками пропадает
    (
        "backend/repository.py",
        'return "\\n---\\n".join(parts)',
        'return "".join(parts)',
    ),
    # find_or_create_hr: по нику подхватывается и запись с чужим идентификатором
    (
        "backend/repository.py",
        "                    HR.telegram_user_id.is_(None)," + CRLF,
        "",
    ),
    # find_or_create_hr: аватар затирает уже сохранённый
    (
        "backend/repository.py",
        "if avatar is not None and hr.avatar is None:",
        "if avatar is not None:",
    ),
    # find_or_create_hr: имя из Telegram затирает введённое пользователем
    (
        "backend/repository.py",
        "    if not hr.name and full_name:",
        "    if full_name:",
    ),
]
