"""Поломки для той части `backend/repository.py`, что отвечает за вакансии.

Каждая — то, что легко испортить случайно: снятое условие отбора, перевёрнутое
сравнение, наибольшее вместо наименьшего, перепутанная карта приоритетов,
потерянный разрешитель спора.
"""

MUTATIONS = [
    # list_vacancies: недоразобранные вакансии перестают отсеиваться
    (
        "backend/repository.py",
        "where_clauses = [Vacancy.is_parsed.is_(True)]",
        "where_clauses = []",
    ),
    # list_vacancies: нижняя граница баллов становится строгой
    (
        "backend/repository.py",
        "where_clauses.append(Vacancy.score >= score_min)",
        "where_clauses.append(Vacancy.score > score_min)",
    ),
    # list_vacancies: «с контактом HR» и «без контакта» меняются местами
    (
        "backend/repository.py",
        "where_clauses.append(Vacancy.hr_id.is_not(None))",
        "where_clauses.append(Vacancy.hr_id.is_(None))",
    ),
    # list_vacancies: у «сначала новых по статусу» подменена карта приоритетов
    (
        "backend/repository.py",
        "*[(Vacancy.status == s, p) for s, p in _STATUS_PRIORITY_NEW_FIRST.items()],",
        "*[(Vacancy.status == s, p) for s, p in _STATUS_PRIORITY_ACTIVE_FIRST.items()],",
    ),
    # list_vacancies: у событий берётся наименьшее время вместо наибольшего
    (
        "backend/repository.py",
        'func.max(VacancyEvent.created_at).label("max_at"),',
        'func.min(VacancyEvent.created_at).label("max_at"),',
    ),
    # list_vacancies: у истории статусов берётся наименьшее время
    (
        "backend/repository.py",
        'func.max(VacancyStatusHistory.changed_at).label("max_at"),',
        'func.min(VacancyStatusHistory.changed_at).label("max_at"),',
    ),
    # list_vacancies: пропадает разрешитель спора у «сначала новых»
    (
        "backend/repository.py",
        "order_by = (activity_ts.desc().nulls_last(), Vacancy.id.desc())",
        "order_by = (activity_ts.desc().nulls_last(),)",
    ),
    # list_vacancies: у «сначала старых» разрешитель спора смотрит в другую сторону
    (
        "backend/repository.py",
        "order_by = (activity_ts.asc().nulls_last(), Vacancy.id.asc())",
        "order_by = (activity_ts.asc().nulls_last(), Vacancy.id.desc())",
    ),
    # list_vacancies: предел страницы применяется и при отборе по зарплате
    (
        "backend/repository.py",
        "if limit is not None and not has_salary_filter:",
        "if limit is not None:",
    ),
    # list_vacancies: верхняя граница зарплаты сравнивается не с тем концом
    (
        "backend/repository.py",
        "if salary_min is not None and hi < salary_min:",
        "if salary_min is not None and lo < salary_min:",
    ),
    # _parse_usd_range: суффикс тысяч перестаёт умножать
    (
        "backend/repository.py",
        "values.append(num * 1000 if has_k else num)",
        "values.append(num)",
    ),
    # _parse_usd_range: границы диапазона меняются местами
    (
        "backend/repository.py",
        "return min(values), max(values)",
        "return max(values), min(values)",
    ),
    # list_vacancy_filter_options: прочерк перестаёт отсеиваться
    (
        "backend/repository.py",
        'if not cleaned or cleaned == "—":',
        "if not cleaned:",
    ),
    # list_vacancy_filter_options: схлопывание написаний компании становится точным
    (
        "backend/repository.py",
        "key = cleaned.lower()",
        "key = cleaned",
    ),
    # list_vacancy_last_activity: у событий берётся наименьшее время
    (
        "backend/repository.py",
        'func.max(VacancyEvent.created_at).label("max_event_at"),',
        'func.min(VacancyEvent.created_at).label("max_event_at"),',
    ),
    # list_vacancy_last_activity: у истории берётся наименьшее время
    (
        "backend/repository.py",
        'func.max(VacancyStatusHistory.changed_at).label("max_status_at"),',
        'func.min(VacancyStatusHistory.changed_at).label("max_status_at"),',
    ),
    # get_vacancy_detail: история отдаётся от ранней записи к поздней
    (
        "backend/repository.py",
        "VacancyStatusHistory.changed_at.desc(),",
        "VacancyStatusHistory.changed_at.asc(),",
    ),
    # get_vacancy_detail: пропадает разрешитель спора в истории
    (
        "backend/repository.py",
        "VacancyStatusHistory.id.desc(),",
        "VacancyStatusHistory.id.asc(),",
    ),
    # get_vacancy_detail: события отдаются от раннего к позднему
    (
        "backend/repository.py",
        "VacancyEvent.created_at.desc(),",
        "VacancyEvent.created_at.asc(),",
    ),
    # update_vacancy_notes: заметка из одних пробелов больше не стирается
    (
        "backend/repository.py",
        "if notes is None or not notes.strip():",
        "if notes is None:",
    ),
    # update_vacancy_notes: пробелы вокруг заметки срезаются
    (
        "backend/repository.py",
        "        normalized = notes\n",
        "        normalized = notes.strip()\n",
    ),
    # set_vacancy_hr: пропадает охрана от повторной привязки того же HR
    (
        "backend/repository.py",
        "if previous_hr_id == hr_id:",
        "if False:",
    ),
    # set_vacancy_company: пропадает охрана от повторной привязки той же компании
    (
        "backend/repository.py",
        "if previous_company_id == company_id:",
        "if False:",
    ),
    # change_vacancy_status: комментарий без смены статуса помечается применённым
    (
        "backend/repository.py",
        "        applied=status_changed,\n",
        "        applied=True,\n",
    ),
    # add_vacancy_event: пустая нагрузка записывается пустым словарём
    (
        "backend/repository.py",
        "        payload=(payload or None),\n",
        "        payload=payload,\n",
    ),
    # apply_classification: граф переходов перестаёт что-либо запрещать
    (
        "backend/repository.py",
        "applied = should_apply_status(previous, classification.status)",
        "applied = True",
    ),
    # mark_ghosted_vacancies: наши собственные сообщения начинают считаться ответом
    (
        "backend/repository.py",
        "        .where(Message.is_incoming.is_(True))\n",
        "        .where(Message.is_incoming.is_(False))\n",
    ),
    # mark_ghosted_vacancies: в счёт идёт история любого статуса, а не нынешнего
    (
        "backend/repository.py",
        "                    last_status_subq.c.status == Vacancy.status,",
        "                    last_status_subq.c.status != Vacancy.status,",
    ),
    # list_vacancies_for_hr: недоразобранные перестают отсеиваться
    (
        "backend/repository.py",
        ".where(Vacancy.hr_id == hr_id, Vacancy.is_parsed.is_(True))",
        ".where(Vacancy.hr_id == hr_id)",
    ),
    # list_vacancies_for_company: недоразобранные перестают отсеиваться
    (
        "backend/repository.py",
        ".where(Vacancy.company_id == company_id, Vacancy.is_parsed.is_(True))",
        ".where(Vacancy.company_id == company_id)",
    ),
    # list_vacancies_for_channel: дата появления берётся от создания, а не от публикации
    (
        "backend/repository.py",
        "activity = func.coalesce(Vacancy.posted_at, Vacancy.created_at)",
        "activity = func.coalesce(Vacancy.created_at, Vacancy.posted_at)",
    ),
    # list_vacancies_for_channel: порядок по горячести статуса перевёрнут
    (
        "backend/repository.py",
        "order_by(status_rank.asc(), activity.desc(), Vacancy.id.desc())",
        "order_by(status_rank.desc(), activity.desc(), Vacancy.id.desc())",
    ),
]
