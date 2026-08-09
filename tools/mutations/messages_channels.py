"""Поломки для `backend/repository/messages.py` и `channels.py`.

Где поломка захватывает конец строки, перевод пишется через `CRLF`: рабочее
дерево здесь с виндовыми переводами, и поиск по `\\n` не находит ничего.
"""

CRLF = "\r\n"

MUTATIONS = [
    # save_incoming_message: сообщение записывается как исходящее
    (
        "backend/repository/messages.py",
        "        is_incoming=True," + CRLF + "        hr_id=hr_id," + CRLF,
        "        is_incoming=False," + CRLF + "        hr_id=hr_id," + CRLF,
    ),
    # save_incoming_message: время подменяется серверным умолчанием
    (
        "backend/repository/messages.py",
        "        sent_at=received_at," + CRLF,
        "",
    ),
    # save_incoming_message: имя вложения теряется
    (
        "backend/repository/messages.py",
        "        media_name=media_name," + CRLF,
        "",
    ),
    # list_messages_for_hr: составной указатель вырождается в сравнение по времени
    (
        "backend/repository/messages.py",
        "                and_(" + CRLF
        + "                    Message.sent_at == before_sent_at," + CRLF
        + "                    Message.id < before_id," + CRLF
        + "                )," + CRLF,
        "",
    ),
    # list_messages_for_hr: указатель отдаёт и себя самого
    (
        "backend/repository/messages.py",
        "                Message.sent_at < before_sent_at,",
        "                Message.sent_at <= before_sent_at,",
    ),
    # list_messages_for_hr: запасной путь по одному номеру пропадает
    (
        "backend/repository/messages.py",
        "        q = q.where(Message.id < before_id)",
        "        pass",
    ),
    # list_messages_for_hr: страница выбирается без запаса, «есть ещё» всегда ложь
    (
        "backend/repository/messages.py",
        "            .limit(limit + 1)",
        "            .limit(limit)",
    ),
    # list_messages_for_hr: порядок не переворачивается перед выдачей
    (
        "backend/repository/messages.py",
        "    return list(reversed(rows)), has_more",
        "    return list(rows), has_more",
    ),
    # list_messages_for_hr: разрешитель спора по номеру строки пропадает
    (
        "backend/repository/messages.py",
        "            q.order_by(Message.sent_at.desc(), Message.id.desc())",
        "            q.order_by(Message.sent_at.desc())",
    ),
    # count_unread_incoming: удалённые снова раздувают счётчик
    (
        "backend/repository/messages.py",
        "            Message.is_incoming," + CRLF
        + "            Message.read_at.is_(None)," + CRLF
        + "            Message.is_deleted.is_(False)," + CRLF,
        "            Message.is_incoming," + CRLF
        + "            Message.read_at.is_(None)," + CRLF,
    ),
    # count_unread_incoming: наши собственные сообщения попадают в счётчик
    (
        "backend/repository/messages.py",
        "        select(func.count(Message.id)).where(" + CRLF
        + "            Message.is_incoming," + CRLF,
        "        select(func.count(Message.id)).where(" + CRLF,
    ),
    # list_hrs_with_unread: список идёт от старого непрочитанного к свежему
    (
        "backend/repository/hr_list.py",
        "            .order_by(func.max(Message.sent_at).desc())",
        "            .order_by(func.max(Message.sent_at).asc())",
    ),
    # list_hrs_with_unread: свежесть меряется по всей переписке, а не по непрочитанному
    (
        "backend/repository/hr_list.py",
        "                Message.is_incoming," + CRLF
        + "                Message.read_at.is_(None)," + CRLF
        + "                Message.is_deleted.is_(False)," + CRLF
        + "            )" + CRLF
        + "            .group_by(HR.id)" + CRLF
        + "            .order_by(func.max(Message.sent_at).desc())",
        "                Message.is_incoming," + CRLF
        + "                Message.is_deleted.is_(False)," + CRLF
        + "            )" + CRLF
        + "            .group_by(HR.id)" + CRLF
        + "            .order_by(func.max(Message.sent_at).desc())",
    ),
    # channel_blacklist_candidates: собачка перед ником пропадает
    (
        "backend/repository/channels.py",
        '    return [f"@{ch.username}"]',
        "    return [ch.username]",
    ),
    # channel_blacklist_preferred_value: кнопка пишет ник без собачки
    (
        "backend/repository/channels.py",
        '    return f"@{ch.username}"' + CRLF,
        "    return ch.username" + CRLF,
    ),
    # _channel_blacklist_value: выключенные отметки снова видны
    (
        "backend/repository/channels.py",
        '                Blacklist.kind == "channel",' + CRLF
        + "                Blacklist.value.in_(candidates)," + CRLF
        + "                Blacklist.active.is_(True)," + CRLF,
        '                Blacklist.kind == "channel",' + CRLF
        + "                Blacklist.value.in_(candidates)," + CRLF,
    ),
    # list_telegram_channels: ник вместо пустого заголовка не подставляется
    (
        "backend/repository/channels.py",
        "    title_or_username = func.coalesce(TelegramChannel.title, TelegramChannel.username)",
        "    title_or_username = TelegramChannel.title",
    ),
    # list_telegram_channels: порядок теряет разрешитель по заголовку
    (
        "backend/repository/channels.py",
        "            func.count(Vacancy.id).desc()," + CRLF
        + "            title_or_username.asc()," + CRLF,
        "            func.count(Vacancy.id).desc()," + CRLF,
    ),
    # list_telegram_channels: поиск перестаёт смотреть в ник
    (
        "backend/repository/channels.py",
        '                or q in (ch.username or "").casefold()' + CRLF,
        "",
    ),
    # _percent_or_none: пустое основание даёт ноль вместо отсутствия
    (
        "backend/repository/channels.py",
        "    if denominator <= 0:" + CRLF + "        return None" + CRLF,
        "    if denominator < 0:" + CRLF + "        return None" + CRLF,
    ),
    # _percent_or_none: округление заменяется отбрасыванием
    (
        "backend/repository/channels.py",
        "    return int(round(numerator / denominator * 100))",
        "    return int(numerator / denominator * 100)",
    ),
    # get_channel_detail: доля откликов считается от общего, а не от подошедшего
    (
        "backend/repository/channels.py",
        "            apply_percent=_percent_or_none(applied_total, fit_total),",
        "            apply_percent=_percent_or_none(applied_total, total),",
    ),
    # get_channel_detail: доля ответов считается от общего
    (
        "backend/repository/channels.py",
        "            response_percent=_percent_or_none(responded_total, applied_total),",
        "            response_percent=_percent_or_none(responded_total, total),",
    ),
    # get_channel_detail: в разбивке остаются только встреченные статусы
    (
        "backend/repository/channels.py",
        "        status.value: counts_by_enum.get(status, 0) for status in VacancyStatus",
        "        status.value: n for status, n in counts_by_enum.items()",
    ),
    # get_channel_detail: темп считается по всей истории
    (
        "backend/repository/channels.py",
        "                    Vacancy.created_at >= since," + CRLF,
        "",
    ),
    # get_channel_detail: чужие вакансии попадают в разбивку
    (
        "backend/repository/channels.py",
        "            .where(Vacancy.source_channel_id == channel_id)" + CRLF
        + "            .group_by(Vacancy.status)" + CRLF,
        "            .group_by(Vacancy.status)" + CRLF,
    ),
    # find_channel_by_username: поиск начинает различать регистр
    (
        "backend/repository/channels.py",
        "            func.lower(TelegramChannel.username) == username.lower()",
        "            TelegramChannel.username == username",
    ),
    # set_channel_active: переключение не доходит до строки
    (
        "backend/repository/channels.py",
        "    ch.is_active = bool(is_active)" + CRLF,
        "",
    ),
    # deactivate_blacklisted_channels: гасятся все каналы подряд
    (
        "backend/repository/channels.py",
        "        if any(c in bl_values for c in channel_blacklist_candidates(ch)):",
        "        if True:",
    ),
    # deactivate_blacklisted_channels: уже выключенные считаются заново
    (
        "backend/repository/channels.py",
        "            select(TelegramChannel).where(TelegramChannel.is_active.is_(True))",
        "            select(TelegramChannel)",
    ),
    # is_channel_blacklisted: несуществующий канал считается внесённым
    (
        "backend/repository/channels.py",
        "    if ch is None:" + CRLF + "        return False" + CRLF
        + "    return await _channel_blacklist_value(session, ch) is not None",
        "    return await _channel_blacklist_value(session, ch) is not None",
    ),
    # set_all_channels_active: оптовое включение перестаёт обходить чёрный список
    (
        "backend/repository/channels.py",
        "            stmt = stmt.where(TelegramChannel.username.notin_(stripped))",
        "            pass",
    ),
    # set_all_channels_active: обход идёт по значению с собачкой
    (
        "backend/repository/channels.py",
        '            stripped = [v.lstrip("@") for v in bl_values]',
        "            stripped = list(bl_values)",
    ),
    # set_all_channels_active: обход применяется и к выключению
    (
        "backend/repository/channels.py",
        "    if is_active:" + CRLF + "        bl_values = list(",
        "    if True:" + CRLF + "        bl_values = list(",
    ),
    # reset_channel_cursor: отметка не стирается
    (
        "backend/repository/channels.py",
        "    ch.last_processed_msg_id = None" + CRLF,
        "",
    ),
    # delete_channel: вакансии не отвязываются
    (
        "backend/repository/channels.py",
        "            update(Vacancy)" + CRLF
        + "            .where(Vacancy.source_channel_id == channel_id)" + CRLF
        + "            .values(source_channel_id=None)" + CRLF,
        "            update(Vacancy)" + CRLF
        + "            .where(Vacancy.source_channel_id == -1)" + CRLF
        + "            .values(source_channel_id=None)" + CRLF,
    ),
]
