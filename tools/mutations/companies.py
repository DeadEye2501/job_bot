"""Поломки для `backend/repository/companies_matching.py` и `companies_card.py`.

Где поломка захватывает конец строки, перевод пишется через `CRLF`: рабочее
дерево здесь с виндовыми переводами, и поиск по `\\n` не находит ничего.
"""

CRLF = "\r\n"

MUTATIONS = [
    # _translit_cyr_to_latin: регистр перестаёт опускаться
    (
        "backend/repository/companies_matching.py",
        'return "".join(_CYR_TO_LAT.get(ch, ch) for ch in s.lower())',
        'return "".join(_CYR_TO_LAT.get(ch, ch) for ch in s)',
    ),
    # _normalize_company_name: кавычки не вырезаются
    (
        "backend/repository/companies_matching.py",
        's = "".join(ch for ch in s.strip() if ch not in _QUOTE_CHARS)',
        "s = s.strip()",
    ),
    # _normalize_company_name: юридическая форма не срезается
    (
        "backend/repository/companies_matching.py",
        '    s = _LEGAL_SUFFIX_RE.sub(" ", s)' + CRLF,
        "",
    ),
    # _normalize_company_name: лишние пробелы не схлопываются
    (
        "backend/repository/companies_matching.py",
        '    return " ".join(s.split())',
        "    return s",
    ),
    # _normalize_host: запрос не срезается
    (
        "backend/repository/companies_matching.py",
        '    s = s.split("?", 1)[0]' + CRLF,
        "",
    ),
    # _normalize_host: порт не срезается
    (
        "backend/repository/companies_matching.py",
        '    s = s.split(":", 1)[0]' + CRLF,
        "",
    ),
    # _normalize_host: www не срезается
    (
        "backend/repository/companies_matching.py",
        '    if s.startswith("www."):',
        "    if False:",
    ),
    # _normalize_host: завершающая точка остаётся
    (
        "backend/repository/companies_matching.py",
        '    s = s.rstrip(".")' + CRLF,
        "",
    ),
    # _is_aggregator_host: поддомены агрегатора больше не опознаются
    (
        "backend/repository/companies_matching.py",
        'if host == h or host.endswith("." + h):',
        "if host == h:",
    ),
    # _signal_host: агрегатор снова считается сигналом о компании
    (
        "backend/repository/companies_matching.py",
        "    if not host or _is_aggregator_host(host):",
        "    if not host:",
    ),
    # _real_corporate_website: ссылка на канал сохраняется как сайт
    (
        "backend/repository/companies_matching.py",
        "    if not _signal_host(_normalize_host(cleaned)):",
        "    if False:",
    ),
    # _hosts_compatible: пустой хост начинает блокировать сведение
    (
        "backend/repository/companies_matching.py",
        "    if not a or not b:" + CRLF + "        return True" + CRLF,
        "",
    ),
    # _enrich_company_with_parsed: сайт затирается поверх имеющегося
    (
        "backend/repository/companies_matching.py",
        "    if real_website and not company.website:",
        "    if real_website:",
    ),
    # _enrich_company_with_parsed: известное написание записывается второй раз
    (
        "backend/repository/companies_matching.py",
        "        if parsed_norm not in existing_norms:",
        "        if True:",
    ),
    # _create_company_row: ссылка на канал оседает сайтом новой компании
    (
        "backend/repository/companies_matching.py",
        "    persisted_website = _real_corporate_website(website)",
        "    persisted_website = website",
    ),
    # _create_company_row: отметка «модель спрашивали» теряется
    (
        "backend/repository/companies_matching.py",
        '        decision["pre_create_stage"] = prior_stage' + CRLF,
        "",
    ),
    # find_or_create_company: пустое имя больше не отсекается
    (
        "backend/repository/companies_matching.py",
        "    if not raw_name:" + CRLF + "        return None, decision" + CRLF,
        "",
    ),
    # find_or_create_company: правило имени перестаёт считаться с сайтами
    (
        "backend/repository/companies_matching.py",
        "                and _hosts_compatible(c_host, parsed_host)" + CRLF,
        "",
    ),
    # find_or_create_company: правило написаний перестаёт считаться с сайтами
    (
        "backend/repository/companies_matching.py",
        "            ) and _hosts_compatible(c_host, parsed_host):",
        "            ):",
    ),
    # find_or_create_company: порог схожести опущен
    (
        "backend/repository/companies_matching.py",
        "            if best >= 0.7:",
        "            if best >= 0.5:",
    ),
    # find_or_create_company: кандидаты перестают упорядочиваться по близости
    (
        "backend/repository/companies_matching.py",
        "        candidates.sort(key=lambda x: -x[1])" + CRLF,
        "",
    ),
    # find_or_create_company: потолок кандидатов поднят
    (
        "backend/repository/companies_matching.py",
        "        candidates = candidates[:5]",
        "        candidates = candidates[:10]",
    ),
    # find_or_create_company: выдуманный номер принимается
    (
        "backend/repository/companies_matching.py",
        "                match = next(" + CRLF
        + "                    (c for c in shortlist if c.id == matched_id), None" + CRLF
        + "                )",
        "                match = next(" + CRLF
        + "                    (c for c in norms_ignored for norms_ignored in []), None" + CRLF
        + "                ) or await session.get(Company, matched_id)",
    ),
    # get_company_detail: счётчик HR перестаёт быть уникализирующим
    (
        "backend/repository/companies_card.py",
        "            select(func.count(func.distinct(Vacancy.hr_id))).where(",
        "            select(func.count(Vacancy.hr_id)).where(",
    ),
    # _company_blacklist_value: выключенные отметки снова видны
    (
        "backend/repository/companies_card.py",
        '                Blacklist.kind == "company",' + CRLF
        + "                Blacklist.value.in_(candidates)," + CRLF
        + "                Blacklist.active.is_(True)," + CRLF,
        '                Blacklist.kind == "company",' + CRLF
        + "                Blacklist.value.in_(candidates)," + CRLF,
    ),
    # list_hrs_for_company: порядок теряет разрешитель по имени
    (
        "backend/repository/hr_list.py",
        "            .where(Vacancy.company_id == company_id)" + CRLF
        + "            .group_by(HR.id)" + CRLF
        + "            .order_by(func.count(Vacancy.id).desc(), HR.name.asc())",
        "            .where(Vacancy.company_id == company_id)" + CRLF
        + "            .group_by(HR.id)" + CRLF
        + "            .order_by(func.count(Vacancy.id).desc())",
    ),
    # list_companies_with_counts: порядок теряет разрешитель по имени
    (
        "backend/repository/companies_list.py",
        ".order_by(func.count(Vacancy.id).desc(), Company.name.asc())",
        ".order_by(func.count(Vacancy.id).desc())",
    ),
    # list_companies_with_counts: поиск перестаёт смотреть в написания
    (
        "backend/repository/companies_list.py",
        "                for alias in (co.aliases or []):" + CRLF
        + "                    if isinstance(alias, str) and q in alias.casefold():" + CRLF
        + "                        return True" + CRLF,
        "",
    ),
    # list_companies_with_counts: поиск перестаёт смотреть в сайт
    (
        "backend/repository/companies_list.py",
        "                if co.website and q in co.website.casefold():" + CRLF
        + "                    return True" + CRLF,
        "",
    ),
    # list_companies_with_counts: страница режется до отбора
    (
        "backend/repository/companies_list.py",
        "        rows = rows[offset : offset + limit]",
        "        rows = rows[offset:offset]",
    ),
    # create_company: пустое имя больше не отвергается
    (
        "backend/repository/companies_card.py",
        '        raise ValueError("create_company: name is required")',
        "        normalized = name",
    ),
    # update_company_fields: пустое имя перестаёт отменять правку
    (
        "backend/repository/companies_card.py",
        "        if not cleaned:" + CRLF
        + "            return False  # company name is required (UNIQUE NOT NULL)" + CRLF,
        "",
    ),
    # update_company_fields: повторы в написаниях перестают отсеиваться
    (
        "backend/repository/companies_card.py",
        "            if s and s.casefold() not in seen:",
        "            if s:",
    ),
    # delete_company: вакансии удаляются вместе с компанией
    (
        "backend/repository/companies_card.py",
        "            update(Vacancy)" + CRLF
        + "            .where(Vacancy.company_id == company_id)" + CRLF
        + "            .values(company_id=None)" + CRLF,
        "            delete(Vacancy).where(Vacancy.company_id == company_id)" + CRLF,
    ),
    # merge_company: имя поглощённой не попадает в написания
    (
        "backend/repository/companies_card.py",
        "    for candidate in abs_aliases + [abs_name]:",
        "    for candidate in abs_aliases:",
    ),
    # merge_company: повтор написания добавляется второй раз
    (
        "backend/repository/companies_card.py",
        "        if candidate and candidate.casefold() not in seen:",
        "        if candidate:",
    ),
    # merge_company: чужой сайт затирает свой
    (
        "backend/repository/companies_card.py",
        "    if not survivor.website and abs_website:",
        "    if abs_website:",
    ),
    # merge_company: слияние записи самой с собой проходит
    (
        "backend/repository/companies_card.py",
        '        raise ValueError("merge_company: absorbed_id == survivor_id")',
        "        return None",
    ),
]
