"""Поломки для той части `backend/repository.py`, что отвечает за статистику.

Где поломка захватывает конец строки, перевод пишется через `CRLF`: рабочее
дерево здесь с виндовыми переводами, и поиск по `\\n` не находит ничего.
"""

CRLF = "\r\n"

MUTATIONS = [
    # _stats_period_since: «сегодня» отсчитывается от текущего часа
    (
        "backend/repository.py",
        '        return now.replace(hour=0, minute=0, second=0, microsecond=0)',
        "        return now",
    ),
    # _stats_period_since: неделя стала месяцем
    (
        "backend/repository.py",
        '    if period == "week":' + CRLF + "        return now - timedelta(days=7)" + CRLF,
        '    if period == "week":' + CRLF + "        return now - timedelta(days=30)" + CRLF,
    ),
    # _stats_period_since: квартал стал месяцем
    (
        "backend/repository.py",
        '    if period == "quarter":' + CRLF + "        return now - timedelta(days=90)" + CRLF,
        '    if period == "quarter":' + CRLF + "        return now - timedelta(days=30)" + CRLF,
    ),
    # get_stats_kpi: общий счётчик считает и недоразобранные
    (
        "backend/repository.py",
        "    base_filter = [Vacancy.is_parsed.is_(True)]" + CRLF + CRLF + "    total = int(",
        "    base_filter = []" + CRLF + CRLF + "    total = int(",
    ),
    # get_stats_kpi: вакансия считается столько раз, сколько раз переходила
    (
        "backend/repository.py",
        "        select(func.count(func.distinct(VacancyStatusHistory.vacancy_id))).where(" + CRLF
        + "            VacancyStatusHistory.status == VacancyStatus.APPLIED," + CRLF,
        "        select(func.count(VacancyStatusHistory.vacancy_id)).where(" + CRLF
        + "            VacancyStatusHistory.status == VacancyStatus.APPLIED," + CRLF,
    ),
    # get_stats_kpi: «в работе» перестаёт считать тестовые задания
    (
        "backend/repository.py",
        "    in_progress_set = {VacancyStatus.INVITATION, VacancyStatus.TEST}",
        "    in_progress_set = {VacancyStatus.INVITATION}",
    ),
    # get_stats_kpi: прибавка считается по последнему переходу
    (
        "backend/repository.py",
        '                    func.min(VacancyStatusHistory.changed_at).label("first_at"),',
        '                    func.max(VacancyStatusHistory.changed_at).label("first_at"),',
    ),
    # get_stats_kpi: прибавка к общему счётчику не отсекается окном
    (
        "backend/repository.py",
        "        period_filter = [*base_filter, Vacancy.created_at >= since]",
        "        period_filter = [*base_filter]",
    ),
    # get_stats_kpi: прибавки считаются и за всё время
    (
        "backend/repository.py",
        "    if since is not None:" + CRLF + "        period_filter = [*base_filter",
        "    if True:" + CRLF + "        period_filter = [*base_filter",
    ),
    # get_stats_status_breakdown: недоразобранные попадают в разбивку
    (
        "backend/repository.py",
        "    base = select(Vacancy.status, func.count(Vacancy.id)).where(" + CRLF
        + "        Vacancy.is_parsed.is_(True)" + CRLF
        + "    )" + CRLF,
        "    base = select(Vacancy.status, func.count(Vacancy.id))" + CRLF,
    ),
    # get_stats_status_breakdown: невстреченные статусы пропадают из разбивки
    (
        "backend/repository.py",
        "    counts: dict[str, int] = {s.value: 0 for s in VacancyStatus}",
        "    counts: dict[str, int] = {}",
    ),
    # get_stats_status_breakdown: окно перестаёт отсекать
    (
        "backend/repository.py",
        "    if since is not None:" + CRLF
        + "        base = base.where(Vacancy.created_at >= since)" + CRLF,
        "",
    ),
    # get_stats_skills: тег считается столько раз, сколько написан в вакансии
    (
        "backend/repository.py",
        "            if lo in seen_in_row:" + CRLF + "                continue" + CRLF,
        "",
    ),
    # get_stats_skills: написания тега перестают сливаться
    (
        "backend/repository.py",
        "            canon = canon_by_lower.setdefault(lo, tag)",
        "            canon = tag",
    ),
    # get_stats_skills: порог перестаёт отсекать редкое
    (
        "backend/repository.py",
        "        if cnt < min_count:" + CRLF + "            continue" + CRLF,
        "",
    ),
    # get_stats_skills: порядок теряет разрешитель по названию
    (
        "backend/repository.py",
        '    items.sort(key=lambda it: (-it["count"], it["label"].casefold()))',
        '    items.sort(key=lambda it: -it["count"])',
    ),
    # get_stats_skills: предел перестаёт обрезать список
    (
        "backend/repository.py",
        '        "skills": items[:limit],',
        '        "skills": items,',
    ),
    # get_stats_skills: написания навыка не участвуют в отметке «мой»
    (
        "backend/repository.py",
        "        if s.aliases:" + CRLF
        + "            for a in s.aliases:" + CRLF
        + "                if isinstance(a, str) and a.strip():" + CRLF
        + "                    profile_set.add(a.strip().casefold())" + CRLF,
        "",
    ),
    # get_stats_skills: недоразобранные вакансии дают теги
    (
        "backend/repository.py",
        "    base_filter = [Vacancy.is_parsed.is_(True), Vacancy.stack.is_not(None)]",
        "    base_filter = [Vacancy.stack.is_not(None)]",
    ),
    # get_stats_hr_responses: наши письма считаются ответом
    (
        "backend/repository.py",
        "                Message.is_incoming.is_(True)," + CRLF,
        "",
    ),
    # get_stats_hr_responses: удалённые сообщения считаются ответом
    (
        "backend/repository.py",
        "                Message.is_deleted.is_(False)," + CRLF
        + "            )" + CRLF
        + "        )" + CRLF
        + "    ).all()" + CRLF
        + "    first_resp_by_vid",
        "            )" + CRLF
        + "        )" + CRLF
        + "    ).all()" + CRLF
        + "    first_resp_by_vid",
    ),
    # get_stats_hr_responses: ответом считается и пришедшее до отправки
    (
        "backend/repository.py",
        "        if applied_at is None or sent_at <= applied_at:",
        "        if applied_at is None:",
    ),
    # get_stats_hr_responses: ответом считается последнее письмо, а не первое
    (
        "backend/repository.py",
        "        if cur is None or sent_at < cur:",
        "        if cur is None or sent_at > cur:",
    ),
    # get_stats_hr_responses: отсчёт идёт от последнего перехода в «отправлено»
    (
        "backend/repository.py",
        '            func.min(VacancyStatusHistory.changed_at).label("applied_at"),',
        '            func.max(VacancyStatusHistory.changed_at).label("applied_at"),',
    ),
    # get_stats_hr_responses: срединный срок при чётном числе берёт один элемент
    (
        "backend/repository.py",
        "            median_seconds = (deltas[n // 2 - 1] + deltas[n // 2]) / 2",
        "            median_seconds = float(deltas[n // 2])",
    ),
    # get_stats_hr_responses: срединный срок при нечётном числе съезжает
    (
        "backend/repository.py",
        "            median_seconds = float(deltas[n // 2])" + CRLF + "        else:",
        "            median_seconds = float(deltas[n // 2 - 1])" + CRLF + "        else:",
    ),
    # get_stats_hr_responses: сроки перестают упорядочиваться перед взятием середины
    (
        "backend/repository.py",
        "    deltas.sort()" + CRLF,
        "",
    ),
    # get_stats_hr_responses: окно перестаёт отсекать по первой отправке
    (
        "backend/repository.py",
        "        where_clauses.append(first_applied_subq.c.applied_at >= since)",
        "        pass",
    ),
    # get_stats_channels_pipeline: недоразобранные попадают в присланное
    (
        "backend/repository.py",
        "    base_filter = [Vacancy.is_parsed.is_(True)]" + CRLF
        + "    if since is not None:" + CRLF
        + "        base_filter.append(Vacancy.created_at >= since)" + CRLF,
        "    base_filter = []" + CRLF
        + "    if since is not None:" + CRLF
        + "        base_filter.append(Vacancy.created_at >= since)" + CRLF,
    ),
    # get_stats_channels_pipeline: помеченный при повторном разборе мусор не считается
    (
        "backend/repository.py",
        "    trash = trash_events + item[\"_rerun_trash\"]",
        '    trash = trash_events',
    ),
    # get_stats_channels_pipeline: удалённый при разборе мусор не считается присланным
    (
        "backend/repository.py",
        '        total = item["_total_vac"] + trash_events',
        '        total = item["_total_vac"]',
    ),
    # get_stats_channels_pipeline: остаток годного уходит в минус
    (
        "backend/repository.py",
        "        fit = max(0, total - trash - not_fit)",
        "        fit = total - trash - not_fit",
    ),
    # get_stats_channels_pipeline: «ответили» перестаёт считать отказы
    (
        "backend/repository.py",
        "        VacancyStatus.IN_PROGRESS, VacancyStatus.OFFER, VacancyStatus.DECLINE," + CRLF
        + "    }" + CRLF
        + "    invite_set = {",
        "        VacancyStatus.IN_PROGRESS, VacancyStatus.OFFER," + CRLF
        + "    }" + CRLF
        + "    invite_set = {",
    ),
    # get_stats_channels_pipeline: «продвинулись» начинает считать отказы
    (
        "backend/repository.py",
        "        VacancyStatus.INVITATION, VacancyStatus.IN_PROGRESS, VacancyStatus.OFFER," + CRLF
        + "    }" + CRLF,
        "        VacancyStatus.INVITATION, VacancyStatus.IN_PROGRESS, VacancyStatus.OFFER," + CRLF
        + "        VacancyStatus.DECLINE," + CRLF
        + "    }" + CRLF,
    ),
    # get_stats_channels_pipeline: доли считаются от присланного, а не от отправленного
    (
        "backend/repository.py",
        "        conv_answ = (answered / sent * 100) if sent > 0 else None",
        "        conv_answ = (answered / total * 100) if total > 0 else None",
    ),
    # get_stats_channels_pipeline: порядок теряет разрешитель по подписи
    (
        "backend/repository.py",
        '    items.sort(key=lambda it: (-it["total"], it["label"].casefold()))',
        '    items.sort(key=lambda it: -it["total"])',
    ),
    # get_stats_channels_pipeline: канал с одними отметками о мусоре выпадает
    (
        "backend/repository.py",
        "    if orphan_ids:" + CRLF,
        "    if False:" + CRLF,
    ),
    # get_stats_channels_pipeline: подпись перестаёт отступать к нику
    (
        "backend/repository.py",
        '                "label": title or (f"@{username}" if username else f"#{ch_id}"),' + CRLF
        + '                "_total_vac": 0,',
        '                "label": title,' + CRLF + '                "_total_vac": 0,',
    ),
]
