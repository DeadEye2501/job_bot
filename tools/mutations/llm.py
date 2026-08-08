"""Поломки для `backend/llm.py`.

Где поломка захватывает конец строки, перевод пишется через `CRLF`: рабочее
дерево здесь с виндовыми переводами, и поиск по `\\n` не находит ничего.
"""

CRLF = "\r\n"

MUTATIONS = [
    # _extract_last_json: берётся первый объект вместо последнего
    (
        "backend/llm.py",
        "    return matches[-1] if matches else None",
        "    return matches[0] if matches else None",
    ),
    # _extract_last_json: кавычки не выпрямляются
    (
        "backend/llm.py",
        "    cleaned = answer.translate(_QUOTE_TRANSLATION)",
        "    cleaned = answer",
    ),
    # _normalize_enum: регистр перестаёт опускаться
    (
        "backend/llm.py",
        "    v = value.strip().lower()",
        "    v = value.strip()",
    ),
    # _normalize_enum: значение вне набора проходит
    (
        "backend/llm.py",
        "    if v in allowed:" + CRLF + "        return v" + CRLF + "    return None",
        "    return v",
    ),
    # _parse_classification: статус сверяется с учётом регистра
    (
        "backend/llm.py",
        "        (m for m in VacancyStatus if m.value.lower() == normalized),",
        "        (m for m in VacancyStatus if m.value == normalized),",
    ),
    # _parse_classification: пустое пояснение сохраняется пустой строкой
    (
        "backend/llm.py",
        '    explanation = (data.get("explanation") or "").strip() or None',
        '    explanation = (data.get("explanation") or "").strip()',
    ),
    # _strip_version: защита коротких имён пропадает
    (
        "backend/llm.py",
        "    if len(cleaned) < 3 or not any(ch.isalpha() for ch in cleaned):",
        "    if False:",
    ),
    # _strip_version: порог защиты поднят
    (
        "backend/llm.py",
        "    if len(cleaned) < 3 or",
        "    if len(cleaned) < 5 or",
    ),
    # _capitalize_skill: канонический вид названий ломается
    (
        "backend/llm.py",
        "        if any(ch.isupper() for ch in w):" + CRLF
        + "            out.append(w)" + CRLF
        + "            continue" + CRLF,
        "",
    ),
    # _clean_stack_items: строка вместо списка перестаёт делиться запятой
    (
        "backend/llm.py",
        '        items: list = raw.split(",")',
        "        items = []",
    ),
    # _clean_stack_items: повторы перестают отсеиваться
    (
        "backend/llm.py",
        "        if key in seen:" + CRLF + "            continue" + CRLF,
        "",
    ),
    # _clean_stack_items: повтор ищется с учётом регистра
    (
        "backend/llm.py",
        "        key = cleaned.casefold()",
        "        key = cleaned",
    ),
    # _clean_stack_items: не-строки проходят в стек
    (
        "backend/llm.py",
        "        if not isinstance(s, str):" + CRLF + "            continue" + CRLF,
        "",
    ),
    # _parse_vacancy_json: вакансия без заголовка проходит
    (
        "backend/llm.py",
        "    if not title:" + CRLF,
        "    if False:" + CRLF,
    ),
    # _parse_vacancy_json: длинное описание не обрезается
    (
        "backend/llm.py",
        "    if description and len(description) > _DESCRIPTION_MAX_CHARS:",
        "    if False:",
    ),
    # _parse_vacancy_json: старое поле стека берётся всегда
    (
        "backend/llm.py",
        '    if "stack_required" in data or "stack_preferred" in data:',
        "    if False:",
    ),
    # _parse_vacancy_json: ссылка не вырезается из названия компании
    (
        "backend/llm.py",
        "        m = _TRAILING_URL_RE.search(company_name)",
        "        m = None",
    ),
    # _parse_vacancy_json: вырезанная ссылка затирает уже присланный сайт
    (
        "backend/llm.py",
        "                if not company_website:" + CRLF
        + "                    company_website = stripped_url" + CRLF,
        "                company_website = stripped_url" + CRLF,
    ),
    # _parse_vacancy_json: название из одной ссылки опустошается
    (
        "backend/llm.py",
        "            if cleaned_name:" + CRLF + "                company_name = cleaned_name",
        "            if True:" + CRLF + "                company_name = cleaned_name",
    ),
    # classify_hr_reply: пустое сообщение уходит к модели
    (
        "backend/llm.py",
        "    if not text:" + CRLF + "        return None" + CRLF
        + "    # Импорт внутри функции",
        "    # Импорт внутри функции",
    ),
    # classify_hr_reply: «пропала без вести» предлагается модели
    (
        "backend/llm.py",
        "    allowed_set.discard(VacancyStatus.GHOSTING)" + CRLF,
        "",
    ),
    # classify_hr_reply: нынешний статус модели не предлагают
    (
        "backend/llm.py",
        "    allowed_set.add(current_status)" + CRLF,
        "",
    ),
    # classify_hr_reply: переписка обрезается с конца вместо начала
    (
        "backend/llm.py",
        "    text = text[-4000:]",
        "    text = text[:4000]",
    ),
    # classify_hr_reply: ограничители блока не вырезаются
    (
        "backend/llm.py",
        '    text = text.replace("<<<", "").replace(">>>", "")' + CRLF
        + "    logger.debug(" + CRLF
        + '        "classify_hr_reply:',
        "    logger.debug(" + CRLF + '        "classify_hr_reply:',
    ),
    # parse_vacancy: пустой пост уходит к модели
    (
        "backend/llm.py",
        "    if not text:" + CRLF + "        return None" + CRLF + "    text = text[:6000]",
        "    text = text[:6000]",
    ),
    # parse_vacancy: пост обрезается с начала вместо конца
    (
        "backend/llm.py",
        "    text = text[:6000]",
        "    text = text[-6000:]",
    ),
    # parse_vacancy: ограничители блока не вырезаются
    (
        "backend/llm.py",
        '    text = text.replace("<<<", "").replace(">>>", "")' + CRLF
        + "    logger.debug(" + CRLF
        + '        "parse_vacancy:',
        "    logger.debug(" + CRLF + '        "parse_vacancy:',
    ),
    # parse_vacancy: список известных навыков не подставляется
    (
        "backend/llm.py",
        '        "{KNOWN_SKILLS_BLOCK}", _format_known_skills(known_skills)',
        '        "{KNOWN_SKILLS_BLOCK}", "—"',
    ),
    # parse_vacancy: ник канала остаётся контактом HR
    (
        "backend/llm.py",
        "        parsed = replace(parsed, hr_contact=None)" + CRLF,
        "",
    ),
    # parse_vacancy: сравнение с ником канала идёт с учётом регистра
    (
        "backend/llm.py",
        '        == channel_username.lower()',
        "        == channel_username",
    ),
    # _format_grades: незнакомый уровень проходит в промпт
    (
        "backend/llm.py",
        "        if key in _GRADE_LABELS_RU:" + CRLF
        + "            parts.append(_GRADE_LABELS_RU[key])" + CRLF,
        "        parts.append(_GRADE_LABELS_RU.get(key, key))" + CRLF,
    ),
    # _format_languages: язык без уровня попадает в промпт
    (
        "backend/llm.py",
        "        if not lvl:" + CRLF
        + "            # пустой уровень не пропускаем как «— —» — пропускаем сам" + CRLF
        + "            # элемент, чтобы LLM не путал «—» с реальным CEFR-токеном" + CRLF
        + "            continue" + CRLF,
        "",
    ),
    # _format_known_skills: написания навыка не попадают в промпт
    (
        "backend/llm.py",
        '            lines.append(f"- {name} — {\', \'.join(aliases)}")',
        '            lines.append(f"- {name}")',
    ),
    # _parse_fit_validation: незнакомый вердикт проходит
    (
        "backend/llm.py",
        "        else:" + CRLF + "            return None" + CRLF + "    else:" + CRLF
        + "        return None" + CRLF,
        "        else:" + CRLF + '            verdict = "fit"' + CRLF + "    else:" + CRLF
        + "        return None" + CRLF,
    ),
    # _looks_hallucinated: общие маркеры перестают проверяться
    (
        "backend/llm.py",
        "    for reason_re, text_re in _GENERIC_HALLUCINATION_MARKERS:" + CRLF
        + "        if reason_re.search(reason) and not text_re.search(raw_text):" + CRLF
        + "            return reason_re.pattern" + CRLF,
        "",
    ),
    # _looks_hallucinated: маркеры по языкам профиля перестают проверяться
    (
        "backend/llm.py",
        "    for reason_re, text_re in _build_profile_hallucination_markers(profile):" + CRLF
        + "        if reason_re.search(reason) and not text_re.search(raw_text):" + CRLF
        + "            return reason_re.pattern" + CRLF,
        "",
    ),
    # _looks_hallucinated: пересказ данных кандидата перестаёт ловиться
    (
        "backend/llm.py",
        "    for style_re in _REASON_STYLE_VIOLATIONS:" + CRLF
        + "        if style_re.search(reason):" + CRLF
        + "            return style_re.pattern" + CRLF,
        "",
    ),
    # _looks_hallucinated: подкреплённое текстом обоснование тоже считается выдуманным
    (
        "backend/llm.py",
        "        if reason_re.search(reason) and not text_re.search(raw_text):" + CRLF
        + "            return reason_re.pattern" + CRLF
        + "    for reason_re, text_re in _build_profile_hallucination_markers(profile):",
        "        if reason_re.search(reason):" + CRLF
        + "            return reason_re.pattern" + CRLF
        + "    for reason_re, text_re in _build_profile_hallucination_markers(profile):",
    ),
    # validate_vacancy_fit: вердикт «подходит» тоже проверяется на выдуманность
    (
        "backend/llm.py",
        '        parsed_validation.verdict in ("reject", "trash")',
        "        parsed_validation.verdict is not None",
    ),
    # validate_vacancy_fit: мусор переворачивается в «подходит»
    (
        "backend/llm.py",
        '            if parsed_validation.verdict == "reject":',
        "            if True:",
    ),
    # validate_vacancy_fit: у мусора остаётся выдуманное обоснование
    (
        "backend/llm.py",
        '            return FitValidation(verdict="trash", reason=None)',
        "            return parsed_validation",
    ),
    # dedupe_company_with_llm: пустой список кандидатов идёт к модели
    (
        "backend/llm.py",
        "    if not candidates:" + CRLF + '        return None, "no_candidates"' + CRLF,
        "",
    ),
    # dedupe_company_with_llm: номер строкой перестаёт читаться
    (
        "backend/llm.py",
        "        return int(matched_id), reasoning",
        "        return matched_id, reasoning",
    ),
    # dedupe_company_with_llm: непригодный номер роняет вызов
    (
        "backend/llm.py",
        "    except (TypeError, ValueError):" + CRLF
        + "        logger.warning(" + CRLF
        + '            "dedupe_company: invalid matched_id %r in LLM response",',
        "    except KeyError:" + CRLF
        + "        logger.warning(" + CRLF
        + '            "dedupe_company: invalid matched_id %r in LLM response",',
    ),
    # factcheck_cover_letter: отказ перестаёт быть отказом
    (
        "backend/llm.py",
        '    if verdict == "reject":' + CRLF
        + '        logger.debug("factcheck_cover_letter: reject in %.2fs", elapsed)' + CRLF
        + "        return False, issues" + CRLF,
        "",
    ),
    # factcheck_cover_letter: замечаний берётся сколько прислали
    (
        "backend/llm.py",
        "    issues = [x for x in issues_raw if isinstance(x, str)][:3]",
        "    issues = [x for x in issues_raw if isinstance(x, str)]",
    ),
    # factcheck_cover_letter: незнакомый вердикт становится отказом
    (
        "backend/llm.py",
        "        verdict, elapsed," + CRLF + "    )" + CRLF + "    return True, []" + CRLF,
        "        verdict, elapsed," + CRLF + "    )" + CRLF + "    return False, []" + CRLF,
    ),
    # generate_cover_letter: без сведений о кандидате письмо всё равно просят
    (
        "backend/llm.py",
        "    if not profile_block:" + CRLF + "        return None" + CRLF,
        "",
    ),
    # generate_cover_letter: заготовки промпта не подставляются
    (
        "backend/llm.py",
        '    text = raw_text.replace("{title}", title_value).replace("{channel}", channel_value)',
        "    text = raw_text",
    ),
    # generate_cover_letter: скобки в названии вакансии не вычищаются
    (
        "backend/llm.py",
        '        str.maketrans("", "", "{}[]<>")',
        '        str.maketrans("", "", "")',
    ),
    # generate_cover_letter: предел подписи поднят
    (
        "backend/llm.py",
        "    too_many_chars = len(text) > 1024 if text else False",
        "    too_many_chars = len(text) > 4096 if text else False",
    ),
    # generate_cover_letter: оставшиеся заготовки перестают отвергаться
    (
        "backend/llm.py",
        '    has_bracket_placeholder = any(ch in text for ch in "[]{}")',
        "    has_bracket_placeholder = False",
    ),
    # generate_cover_letter: утечка углового шаблона перестаёт отвергаться
    (
        "backend/llm.py",
        "    has_template_leak = bool(_TEMPLATE_PLACEHOLDER_RE.search(text))",
        "    has_template_leak = False",
    ),
    # generate_cover_letter: оборванное письмо отправляется
    (
        "backend/llm.py",
        '    truncated = finish_reason == "length" and bool(text) and text[-1] not in ".!?…"',
        "    truncated = False",
    ),
    # generate_cover_letter: успевшее закончиться письмо считается оборванным
    (
        "backend/llm.py",
        'and bool(text) and text[-1] not in ".!?…"',
        "and bool(text)",
    ),
    # generate_cover_letter: упоминание вложения перестаёт отвергаться
    (
        "backend/llm.py",
        "    mentions_attachment = bool(text and _ATTACHMENT_RE.search(text))",
        "    mentions_attachment = False",
    ),
    # generate_cover_letter: сверка фактов перестаёт влиять на исход
    (
        "backend/llm.py",
        "    ok, issues = await factcheck_cover_letter(profile_block, text, client, model)" + CRLF
        + "    if not ok:" + CRLF,
        "    ok, issues = await factcheck_cover_letter(profile_block, text, client, model)" + CRLF
        + "    if False:" + CRLF,
    ),
    # generate_cover_letter: сверке фактов подаётся текст без подстановок
    (
        "backend/llm.py",
        "    ok, issues = await factcheck_cover_letter(profile_block, text, client, model)",
        "    ok, issues = await factcheck_cover_letter(profile_block, raw_text, client, model)",
    ),
]
