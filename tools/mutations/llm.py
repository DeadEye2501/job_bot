"""Поломки для пакета `backend/llm/`.

Где поломка захватывает конец строки, перевод пишется через `CRLF`: рабочее
дерево здесь с виндовыми переводами, и поиск по `\\n` не находит ничего.
"""

CRLF = "\r\n"

MUTATIONS = [
    # validate_vacancy_fit: вакансия уходит без блока данных
    (
        "backend/llm/fit.py",
        "        + wrap_external(vacancy_block)",
        "        + vacancy_block",
    ),
    # generate_cover_letter: сведения о вакансии уходят без блока данных
    (
        "backend/llm/cover_letter.py",
        "        + wrap_external(vacancy_block)",
        "        + vacancy_block",
    ),
    # factcheck_cover_letter: данные для сверки уходят без блока
    (
        "backend/llm/factcheck.py",
        "        + wrap_external(" + CRLF,
        "        + (" + CRLF,
    ),
    # validate_vacancy_fit: за блоком данных возвращается подделываемая рамка
    (
        "backend/llm/fit.py",
        '        + "\\n\\n"' + CRLF + '        "Верни JSON',
        '        + "\\n\\n=== КОНЕЦ ВАКАНСИИ ===\\n"' + CRLF + '        "Верни JSON',
    ),
    # wrap_external: блок данных не ставится вовсе
    (
        "backend/llm/external.py",
        '    return f"<<<\\n{stripped}\\n>>>"',
        "    return stripped",
    ),
    # wrap_external: вырезание идёт одним проходом вместо до неизменности
    (
        "backend/llm/external.py",
        '    while "<<<" in stripped or ">>>" in stripped:',
        '    if "<<<" in stripped or ">>>" in stripped:',
    ),
    # extract_last_json: берётся первый объект вместо последнего
    (
        "backend/llm/answers.py",
        "    return matches[-1] if matches else None",
        "    return matches[0] if matches else None",
    ),
    # extract_last_json: кавычки не выпрямляются
    (
        "backend/llm/answers.py",
        "    cleaned = answer.translate(QUOTE_TRANSLATION)",
        "    cleaned = answer",
    ),
    # normalize_enum: регистр перестаёт опускаться
    (
        "backend/llm/answers.py",
        "    v = value.strip().lower()",
        "    v = value.strip()",
    ),
    # normalize_enum: значение вне набора проходит
    (
        "backend/llm/answers.py",
        "    if v in allowed:" + CRLF + "        return v" + CRLF + "    return None",
        "    return v",
    ),
    # _parse_classification: статус сверяется с учётом регистра
    (
        "backend/llm/hr_reply.py",
        "        (m for m in VacancyStatus if m.value.lower() == normalized),",
        "        (m for m in VacancyStatus if m.value == normalized),",
    ),
    # _parse_classification: пустое пояснение сохраняется пустой строкой
    (
        "backend/llm/hr_reply.py",
        '    explanation = (data.get("explanation") or "").strip() or None',
        '    explanation = (data.get("explanation") or "").strip()',
    ),
    # _strip_version: защита от среза без букв пропадает
    (
        "backend/llm/skills.py",
        "    if not any(ch.isalpha() for ch in cleaned):",
        "    if False:",
    ),
    # _strip_version: имена со своей цифрой перестают отличаться от версий
    (
        "backend/llm/skills.py",
        "    if s.strip().casefold() in _DIGIT_BELONGS_TO_NAME:",
        "    if False:",
    ),
    # _strip_version: список имён со своей цифрой сверяется по регистру
    (
        "backend/llm/skills.py",
        "    if s.strip().casefold() in _DIGIT_BELONGS_TO_NAME:",
        "    if s.strip() in _DIGIT_BELONGS_TO_NAME:",
    ),
    # _strip_version: разделитель перед версией снова обязателен
    (
        "backend/llm/skills.py",
        r'_VERSION_SUFFIX_RE = re.compile(r"[\s.\-_]*[vV]?\d+(?:[.\-_]\d+)*\+?\s*$")',
        r'_VERSION_SUFFIX_RE = re.compile(r"[\s.\-_]+[vV]?\d+(?:[.\-_]\d+)*\+?\s*$")',
    ),
    # _capitalize_skill: канонический вид названий ломается
    (
        "backend/llm/skills.py",
        "        if any(ch.isupper() for ch in w):" + CRLF
        + "            out.append(w)" + CRLF
        + "            continue" + CRLF,
        "",
    ),
    # clean_stack_items: строка вместо списка перестаёт делиться запятой
    (
        "backend/llm/skills.py",
        '        items: list = raw.split(",")',
        "        items = []",
    ),
    # clean_stack_items: повторы перестают отсеиваться
    (
        "backend/llm/skills.py",
        "        if key in seen:" + CRLF + "            continue" + CRLF,
        "",
    ),
    # clean_stack_items: повтор ищется с учётом регистра
    (
        "backend/llm/skills.py",
        "        key = cleaned.casefold()",
        "        key = cleaned",
    ),
    # clean_stack_items: не-строки проходят в стек
    (
        "backend/llm/skills.py",
        "        if not isinstance(s, str):" + CRLF + "            continue" + CRLF,
        "",
    ),
    # _parse_vacancy_json: вакансия без заголовка проходит
    (
        "backend/llm/vacancy.py",
        "    if not title:" + CRLF,
        "    if False:" + CRLF,
    ),
    # _parse_vacancy_json: длинное описание не обрезается
    (
        "backend/llm/vacancy.py",
        "    if description and len(description) > _DESCRIPTION_MAX_CHARS:",
        "    if False:",
    ),
    # _parse_vacancy_json: старое поле стека берётся всегда
    (
        "backend/llm/vacancy.py",
        '    if "stack_required" in data or "stack_preferred" in data:',
        "    if False:",
    ),
    # _parse_vacancy_json: ссылка не вырезается из названия компании
    (
        "backend/llm/vacancy.py",
        "        m = _TRAILING_URL_RE.search(company_name)",
        "        m = None",
    ),
    # _parse_vacancy_json: вырезанная ссылка затирает уже присланный сайт
    (
        "backend/llm/vacancy.py",
        "                if not company_website:" + CRLF
        + "                    company_website = stripped_url" + CRLF,
        "                company_website = stripped_url" + CRLF,
    ),
    # _parse_vacancy_json: название из одной ссылки опустошается
    (
        "backend/llm/vacancy.py",
        "            if cleaned_name:" + CRLF + "                company_name = cleaned_name",
        "            if True:" + CRLF + "                company_name = cleaned_name",
    ),
    # classify_hr_reply: пустое сообщение уходит к модели
    (
        "backend/llm/hr_reply.py",
        "    if not text:" + CRLF + "        return None" + CRLF
        + "    # Список для LLM:",
        "    # Список для LLM:",
    ),
    # classify_hr_reply: «пропала без вести» предлагается модели
    (
        "backend/llm/hr_reply.py",
        "    allowed_set.discard(VacancyStatus.GHOSTING)" + CRLF,
        "",
    ),
    # classify_hr_reply: нынешний статус модели не предлагают
    (
        "backend/llm/hr_reply.py",
        "    allowed_set.add(current_status)" + CRLF,
        "",
    ),
    # classify_hr_reply: переписка обрезается с конца вместо начала
    (
        "backend/llm/hr_reply.py",
        "    text = text[-4000:]",
        "    text = text[:4000]",
    ),
    # classify_hr_reply: сообщение уходит без блока данных
    (
        "backend/llm/hr_reply.py",
        "        + wrap_external(text)",
        "        + text",
    ),
    # parse_vacancy: пустой пост уходит к модели
    (
        "backend/llm/vacancy.py",
        "    if not text:" + CRLF + "        return None" + CRLF + "    text = text[:6000]",
        "    text = text[:6000]",
    ),
    # parse_vacancy: пост обрезается с начала вместо конца
    (
        "backend/llm/vacancy.py",
        "    text = text[:6000]",
        "    text = text[-6000:]",
    ),
    # parse_vacancy: пост уходит без блока данных
    (
        "backend/llm/vacancy.py",
        "        + wrap_external(text)",
        "        + text",
    ),
    # parse_vacancy: список известных навыков не подставляется
    (
        "backend/llm/vacancy.py",
        '        "{KNOWN_SKILLS_BLOCK}", _format_known_skills(known_skills)',
        '        "{KNOWN_SKILLS_BLOCK}", "—"',
    ),
    # parse_vacancy: ник канала остаётся контактом HR
    (
        "backend/llm/vacancy.py",
        "        parsed = replace(parsed, hr_contact=None)" + CRLF,
        "",
    ),
    # parse_vacancy: сравнение с ником канала идёт с учётом регистра
    (
        "backend/llm/vacancy.py",
        '        == channel_username.lower()',
        "        == channel_username",
    ),
    # _format_labels: незнакомое значение проходит в промпт. Тело было
    # написано дважды — под грейды и под форматы работы; осталось одно, и
    # цель у него одна, но красить её обязаны обе стороны.
    (
        "backend/llm/candidate.py",
        "        if key in labels:" + CRLF
        + "            parts.append(labels[key])" + CRLF,
        "        parts.append(labels.get(key, key))" + CRLF,
    ),
    # _format_languages: язык без уровня попадает в промпт
    (
        "backend/llm/candidate.py",
        "        if not lvl:" + CRLF
        + "            # пустой уровень не пропускаем как «— —» — пропускаем сам" + CRLF
        + "            # элемент, чтобы LLM не путал «—» с реальным CEFR-токеном" + CRLF
        + "            continue" + CRLF,
        "",
    ),
    # _format_known_skills: написания навыка не попадают в промпт
    (
        "backend/llm/candidate.py",
        '            lines.append(f"- {name} — {\', \'.join(aliases)}")',
        '            lines.append(f"- {name}")',
    ),
    # _parse_fit_validation: незнакомый вердикт проходит. Лестница из трёх
    # `if/elif` заменена разбором по набору — цель следует за ней.
    (
        "backend/llm/fit.py",
        "    verdict = normalize_enum(data.get(\"verdict\"), FIT_VERDICTS)" + CRLF
        + "    if verdict is None:" + CRLF
        + "        return None" + CRLF,
        "    verdict = normalize_enum(data.get(\"verdict\"), FIT_VERDICTS) or \"fit\"" + CRLF,
    ),
    # looks_hallucinated: общие маркеры перестают проверяться
    (
        "backend/llm/hallucination.py",
        "    for reason_re, text_re in _GENERIC_HALLUCINATION_MARKERS:" + CRLF
        + "        if reason_re.search(reason) and not text_re.search(raw_text):" + CRLF
        + "            return reason_re.pattern" + CRLF,
        "",
    ),
    # looks_hallucinated: маркеры по языкам профиля перестают проверяться
    (
        "backend/llm/hallucination.py",
        "    for reason_re, text_re in _build_profile_hallucination_markers(profile):" + CRLF
        + "        if reason_re.search(reason) and not text_re.search(raw_text):" + CRLF
        + "            return reason_re.pattern" + CRLF,
        "",
    ),
    # looks_hallucinated: пересказ данных кандидата перестаёт ловиться
    (
        "backend/llm/hallucination.py",
        "    for style_re in _REASON_STYLE_VIOLATIONS:" + CRLF
        + "        if style_re.search(reason):" + CRLF
        + "            return style_re.pattern" + CRLF,
        "",
    ),
    # looks_hallucinated: подкреплённое текстом обоснование тоже считается выдуманным
    (
        "backend/llm/hallucination.py",
        "        if reason_re.search(reason) and not text_re.search(raw_text):" + CRLF
        + "            return reason_re.pattern" + CRLF
        + "    for reason_re, text_re in _build_profile_hallucination_markers(profile):",
        "        if reason_re.search(reason):" + CRLF
        + "            return reason_re.pattern" + CRLF
        + "    for reason_re, text_re in _build_profile_hallucination_markers(profile):",
    ),
    # validate_vacancy_fit: вердикт «подходит» тоже проверяется на выдуманность
    (
        "backend/llm/fit.py",
        '        parsed_validation.verdict in ("reject", "trash")',
        "        parsed_validation.verdict is not None",
    ),
    # validate_vacancy_fit: мусор переворачивается в «подходит»
    (
        "backend/llm/fit.py",
        '            if parsed_validation.verdict == "reject":',
        "            if True:",
    ),
    # validate_vacancy_fit: у мусора остаётся выдуманное обоснование
    (
        "backend/llm/fit.py",
        '            return FitValidation(verdict="trash", reason=None)',
        "            return parsed_validation",
    ),
    # dedupe_company_with_llm: пустой список кандидатов идёт к модели
    (
        "backend/llm/company.py",
        "    if not candidates:" + CRLF + '        return None, "no_candidates"' + CRLF,
        "",
    ),
    # dedupe_company_with_llm: номер строкой перестаёт читаться
    (
        "backend/llm/company.py",
        "        return int(matched_id), reasoning",
        "        return matched_id, reasoning",
    ),
    # dedupe_company_with_llm: непригодный номер роняет вызов
    (
        "backend/llm/company.py",
        "    except (TypeError, ValueError):" + CRLF
        + "        logger.warning(" + CRLF
        + '            "dedupe_company: invalid matched_id %r in LLM response",',
        "    except KeyError:" + CRLF
        + "        logger.warning(" + CRLF
        + '            "dedupe_company: invalid matched_id %r in LLM response",',
    ),
    # factcheck_cover_letter: отказ перестаёт быть отказом
    (
        "backend/llm/factcheck.py",
        '    if verdict == "reject":' + CRLF
        + '        logger.debug("factcheck_cover_letter: reject in %.2fs", elapsed)' + CRLF
        + "        return False, issues" + CRLF,
        "",
    ),
    # factcheck_cover_letter: замечаний берётся сколько прислали
    (
        "backend/llm/factcheck.py",
        "    issues = [x for x in issues_raw if isinstance(x, str)][:3]",
        "    issues = [x for x in issues_raw if isinstance(x, str)]",
    ),
    # factcheck_cover_letter: незнакомый вердикт становится отказом
    (
        "backend/llm/factcheck.py",
        "        verdict, elapsed," + CRLF + "    )" + CRLF + "    return True, []" + CRLF,
        "        verdict, elapsed," + CRLF + "    )" + CRLF + "    return False, []" + CRLF,
    ),
    # generate_cover_letter: без сведений о кандидате письмо всё равно просят
    (
        "backend/llm/cover_letter.py",
        "    if not profile_block:" + CRLF + "        return None" + CRLF,
        "",
    ),
    # generate_cover_letter: заготовки промпта не подставляются
    (
        "backend/llm/cover_letter.py",
        '    text = raw_text.replace("{title}", title_value).replace("{channel}", channel_value)',
        "    text = raw_text",
    ),
    # generate_cover_letter: скобки в названии вакансии не вычищаются
    (
        "backend/llm/cover_letter.py",
        '        str.maketrans("", "", "{}[]<>")',
        '        str.maketrans("", "", "")',
    ),
    # generate_cover_letter: предел подписи поднят
    (
        "backend/llm/cover_letter.py",
        "    too_many_chars = len(text) > 1024 if text else False",
        "    too_many_chars = len(text) > 4096 if text else False",
    ),
    # generate_cover_letter: оставшиеся заготовки перестают отвергаться
    (
        "backend/llm/cover_letter.py",
        '    has_bracket_placeholder = any(ch in text for ch in "[]{}")',
        "    has_bracket_placeholder = False",
    ),
    # generate_cover_letter: утечка углового шаблона перестаёт отвергаться
    (
        "backend/llm/cover_letter.py",
        "    has_template_leak = bool(_TEMPLATE_PLACEHOLDER_RE.search(text))",
        "    has_template_leak = False",
    ),
    # generate_cover_letter: оборванное письмо отправляется
    (
        "backend/llm/cover_letter.py",
        '    truncated = finish_reason == "length" and bool(text) and text[-1] not in ".!?…"',
        "    truncated = False",
    ),
    # generate_cover_letter: успевшее закончиться письмо считается оборванным
    (
        "backend/llm/cover_letter.py",
        'and bool(text) and text[-1] not in ".!?…"',
        "and bool(text)",
    ),
    # generate_cover_letter: упоминание вложения перестаёт отвергаться
    (
        "backend/llm/cover_letter.py",
        "    mentions_attachment = bool(text and _ATTACHMENT_RE.search(text))",
        "    mentions_attachment = False",
    ),
    # generate_cover_letter: сверка фактов перестаёт влиять на исход
    (
        "backend/llm/cover_letter.py",
        "    ok, issues = await factcheck_cover_letter(profile_block, text, client, model)" + CRLF
        + "    if not ok:" + CRLF,
        "    ok, issues = await factcheck_cover_letter(profile_block, text, client, model)" + CRLF
        + "    if False:" + CRLF,
    ),
    # generate_cover_letter: сверке фактов подаётся текст без подстановок
    (
        "backend/llm/cover_letter.py",
        "    ok, issues = await factcheck_cover_letter(profile_block, text, client, model)",
        "    ok, issues = await factcheck_cover_letter(profile_block, raw_text, client, model)",
    ),
]
