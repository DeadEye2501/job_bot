"""Поломки для `backend/repository/stats_summary.py` и `stats_pipeline.py`.

Где поломка захватывает конец строки, перевод пишется через `CRLF`: рабочее
дерево здесь с виндовыми переводами, и поиск по `\\n` не находит ничего.
"""

CRLF = "\r\n"

MUTATIONS = [
    # _stats_period_since: «сегодня» отсчитывается от текущего часа
    (
        "backend/repository/stats_summary.py",
        '        return now.replace(hour=0, minute=0, second=0, microsecond=0)',
        "        return now",
    ),
    # _stats_period_since: неделя стала месяцем
    (
        "backend/repository/stats_summary.py",
        '    if period == "week":' + CRLF + "        return now - timedelta(days=7)" + CRLF,
        '    if period == "week":' + CRLF + "        return now - timedelta(days=30)" + CRLF,
    ),
    # _stats_period_since: квартал стал месяцем
    (
        "backend/repository/stats_summary.py",
        '    if period == "quarter":' + CRLF + "        return now - timedelta(days=90)" + CRLF,
        '    if period == "quarter":' + CRLF + "        return now - timedelta(days=30)" + CRLF,
    ),
    # get_stats_kpi: общий счётчик считает и недоразобранные
    (
        "backend/repository/stats_summary.py",
        "    base_filter = [Vacancy.is_parsed.is_(True)]" + CRLF + CRLF + "    total = int(",
        "    base_filter = []" + CRLF + CRLF + "    total = int(",
    ),
    # _ever_in: вакансия считается столько раз, сколько раз переходила
    (
        "backend/repository/stats_summary.py",
        "            select(func.count(func.distinct(VacancyStatusHistory.vacancy_id)))" + CRLF,
        "            select(func.count(VacancyStatusHistory.vacancy_id))" + CRLF,
    ),
    # _ever_in: в ступени воронки попадают неразобранные вакансии
    (
        "backend/repository/stats_summary.py",
        "            .join(Vacancy, Vacancy.id == VacancyStatusHistory.vacancy_id)" + CRLF
        + "            .where(_status_cond(statuses), *base_filter)" + CRLF,
        "            .where(_status_cond(statuses))" + CRLF,
    ),
    # _first_in_period: в прибавку за период попадают неразобранные
    (
        "backend/repository/stats_summary.py",
        "                .join(Vacancy, Vacancy.id == sub.c.vid)" + CRLF
        + "                .where(sub.c.first_at >= since, *base_filter)" + CRLF,
        "                .where(sub.c.first_at >= since)" + CRLF,
    ),
    # get_stats_kpi: «в работе» перестаёт считать тестовые задания
    (
        "backend/repository/stats_summary.py",
        "    in_progress_set = {VacancyStatus.INVITATION, VacancyStatus.TEST}",
        "    in_progress_set = {VacancyStatus.INVITATION}",
    ),
    # first_transition_subq: прибавка считается по последнему переходу.
    # Подзапрос сведён из двух копий, и цель у него теперь одна — гонять
    # набор надо и против тестов воронки по каналам, второго потребителя.
    (
        "backend/repository/stats_summary.py",
        '            func.min(VacancyStatusHistory.changed_at).label("first_at"),',
        '            func.max(VacancyStatusHistory.changed_at).label("first_at"),',
    ),
    # get_stats_kpi: прибавка к общему счётчику не отсекается окном
    (
        "backend/repository/stats_summary.py",
        "        period_filter = [*base_filter, Vacancy.created_at >= since]",
        "        period_filter = [*base_filter]",
    ),
    # get_stats_kpi: прибавки считаются и за всё время
    (
        "backend/repository/stats_summary.py",
        "    if since is not None:" + CRLF + "        period_filter = [*base_filter",
        "    if True:" + CRLF + "        period_filter = [*base_filter",
    ),
    # get_stats_status_breakdown: недоразобранные попадают в разбивку
    (
        "backend/repository/stats_summary.py",
        "    base = select(Vacancy.status, func.count(Vacancy.id)).where(" + CRLF
        + "        Vacancy.is_parsed.is_(True)" + CRLF
        + "    )" + CRLF,
        "    base = select(Vacancy.status, func.count(Vacancy.id))" + CRLF,
    ),
    # get_stats_status_breakdown: невстреченные статусы пропадают из разбивки
    (
        "backend/repository/stats_summary.py",
        "    counts: dict[str, int] = {s.value: 0 for s in VacancyStatus}",
        "    counts: dict[str, int] = {}",
    ),
    # get_stats_status_breakdown: окно перестаёт отсекать
    (
        "backend/repository/stats_summary.py",
        "    if since is not None:" + CRLF
        + "        base = base.where(Vacancy.created_at >= since)" + CRLF,
        "",
    ),
    # get_stats_skills: тег считается столько раз, сколько написан в вакансии
    (
        "backend/repository/stats_summary.py",
        "            if lo in seen_in_row:" + CRLF + "                continue" + CRLF,
        "",
    ),
    # get_stats_skills: написания тега перестают сливаться
    (
        "backend/repository/stats_summary.py",
        "            canon = canon_by_lower.setdefault(lo, tag)",
        "            canon = tag",
    ),
    # get_stats_skills: порог перестаёт отсекать редкое
    (
        "backend/repository/stats_summary.py",
        "        if cnt < min_count:" + CRLF + "            continue" + CRLF,
        "",
    ),
    # get_stats_skills: порядок теряет разрешитель по названию
    (
        "backend/repository/stats_summary.py",
        '    items.sort(key=lambda it: (-it["count"], it["label"].casefold()))',
        '    items.sort(key=lambda it: -it["count"])',
    ),
    # get_stats_skills: предел перестаёт обрезать список
    (
        "backend/repository/stats_summary.py",
        '        "skills": items[:limit],',
        '        "skills": items,',
    ),
    # get_stats_skills: отметка «мой» перестаёт смотреть на анкету
    (
        "backend/repository/stats_summary.py",
        "    profile_set = build_skill_lookup(list(skill_rows))" + CRLF,
        "    profile_set = set()" + CRLF,
    ),
    # get_stats_skills: ключ технологии считается не тем правилом
    (
        "backend/repository/stats_summary.py",
        '            "mine": skill_key(canon) in profile_set,',
        '            "mine": canon in profile_set,',
    ),
    # get_stats_skills: недоразобранные вакансии дают теги
    (
        "backend/repository/stats_summary.py",
        "    base_filter = [Vacancy.is_parsed.is_(True), Vacancy.stack.is_not(None)]",
        "    base_filter = [Vacancy.stack.is_not(None)]",
    ),
    # get_stats_hr_responses: наши письма считаются ответом
    (
        "backend/repository/stats_summary.py",
        "                Message.is_incoming.is_(True)," + CRLF,
        "",
    ),
    # get_stats_hr_responses: удалённые сообщения считаются ответом
    (
        "backend/repository/stats_summary.py",
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
        "backend/repository/stats_summary.py",
        "        if applied_at is None or sent_at <= applied_at:",
        "        if applied_at is None:",
    ),
    # get_stats_hr_responses: ответом считается последнее письмо, а не первое
    (
        "backend/repository/stats_summary.py",
        "        if cur is None or sent_at < cur:",
        "        if cur is None or sent_at > cur:",
    ),
    # get_stats_hr_responses: отсчёт идёт от последнего перехода в «отправлено»
    (
        "backend/repository/stats_summary.py",
        '            func.min(VacancyStatusHistory.changed_at).label("applied_at"),',
        '            func.max(VacancyStatusHistory.changed_at).label("applied_at"),',
    ),
    # get_stats_hr_responses: срединный срок при чётном числе берёт один элемент
    (
        "backend/repository/stats_summary.py",
        "            median_seconds = (deltas[n // 2 - 1] + deltas[n // 2]) / 2",
        "            median_seconds = float(deltas[n // 2])",
    ),
    # get_stats_hr_responses: срединный срок при нечётном числе съезжает
    (
        "backend/repository/stats_summary.py",
        "            median_seconds = float(deltas[n // 2])" + CRLF + "        else:",
        "            median_seconds = float(deltas[n // 2 - 1])" + CRLF + "        else:",
    ),
    # get_stats_hr_responses: сроки перестают упорядочиваться перед взятием середины
    (
        "backend/repository/stats_summary.py",
        "    deltas.sort()" + CRLF,
        "",
    ),
    # get_stats_hr_responses: окно перестаёт отсекать по первой отправке
    (
        "backend/repository/stats_summary.py",
        "        where_clauses.append(first_applied_subq.c.applied_at >= since)",
        "        pass",
    ),
    # get_stats_channels_pipeline: недоразобранные попадают в присланное
    (
        "backend/repository/stats_pipeline.py",
        "    base_filter = [Vacancy.is_parsed.is_(True)]" + CRLF
        + "    if since is not None:" + CRLF
        + "        base_filter.append(Vacancy.created_at >= since)" + CRLF,
        "    base_filter = []" + CRLF
        + "    if since is not None:" + CRLF
        + "        base_filter.append(Vacancy.created_at >= since)" + CRLF,
    ),
    # get_stats_channels_pipeline: помеченный при повторном разборе мусор не считается
    (
        "backend/repository/stats_pipeline.py",
        "    trash = trash_events + item[\"_rerun_trash\"]",
        '    trash = trash_events',
    ),
    # get_stats_channels_pipeline: удалённый при разборе мусор не считается присланным
    (
        "backend/repository/stats_pipeline.py",
        '        total = item["_total_vac"] + trash_events',
        '        total = item["_total_vac"]',
    ),
    # Перечни воронки уехали в `backend/domain/funnel.py`, цели вместе с ними:
    # они были объявлены и там, и в `channels.py`, а теперь объявлены один раз.
    # RESPONDED: «ответили» перестаёт считать отказы
    (
        "backend/domain/funnel.py",
        "    VacancyStatus.OFFER," + CRLF
        + "    VacancyStatus.DECLINE," + CRLF
        + "})" + CRLF
        + CRLF
        + "# `INVITED`",
        "    VacancyStatus.OFFER," + CRLF
        + "})" + CRLF
        + CRLF
        + "# `INVITED`",
    ),
    # INVITED: «продвинулись» начинает считать отказы
    (
        "backend/domain/funnel.py",
        "INVITED: frozenset[VacancyStatus] = frozenset({" + CRLF
        + "    VacancyStatus.INVITATION," + CRLF,
        "INVITED: frozenset[VacancyStatus] = frozenset({" + CRLF
        + "    VacancyStatus.INVITATION," + CRLF
        + "    VacancyStatus.DECLINE," + CRLF,
    ),
    # get_stats_channels_pipeline: доли считаются от присланного, а не от отправленного
    (
        "backend/repository/stats_pipeline.py",
        "        conv_answ = (answered / sent * 100) if sent > 0 else None",
        "        conv_answ = (answered / total * 100) if total > 0 else None",
    ),
    # get_stats_channels_pipeline: порядок теряет разрешитель по подписи
    (
        "backend/repository/stats_pipeline.py",
        '    items.sort(key=lambda it: (-it["total"], it["label"].casefold()))',
        '    items.sort(key=lambda it: -it["total"])',
    ),
    # get_stats_channels_pipeline: канал с одними отметками о мусоре выпадает
    (
        "backend/repository/stats_pipeline.py",
        "    if orphan_ids:" + CRLF,
        "    if False:" + CRLF,
    ),
    # get_stats_channels_pipeline: подпись перестаёт отступать к нику
    (
        "backend/repository/stats_pipeline.py",
        '                "label": title or (f"@{username}" if username else f"#{ch_id}"),' + CRLF
        + '                "_total_vac": 0,',
        '                "label": title,' + CRLF + '                "_total_vac": 0,',
    ),
]
