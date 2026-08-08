"""Поломки для той части `backend/repository.py`, что отвечает за профиль.

Где поломка захватывает конец строки, перевод пишется через `CRLF`: рабочее
дерево здесь с виндовыми переводами, и поиск по `\\n` не находит ничего.
"""

CRLF = "\r\n"

MUTATIONS = [
    # _normalize_skill_key: разделители перестают схлопываться
    (
        "backend/repository.py",
        '    return _SKILL_KEY_RE.sub(" ", s.strip().lower()).strip()',
        "    return s.strip().lower()",
    ),
    # _normalize_skill_key: регистр перестаёт опускаться
    (
        "backend/repository.py",
        '_SKILL_KEY_RE.sub(" ", s.strip().lower())',
        '_SKILL_KEY_RE.sub(" ", s.strip())',
    ),
    # list_skills: порядок заведения теряется
    (
        "backend/repository.py",
        "    return list(" + CRLF
        + "        (await session.scalars(select(ProfileSkill).order_by(ProfileSkill.id))).all()",
        "    return list(" + CRLF
        + "        (await session.scalars(select(ProfileSkill).order_by(ProfileSkill.name))).all()",
    ),
    # list_experience: места идут от давнего к свежему
    (
        "backend/repository.py",
        "                .order_by(ProfileExperience.start_date.desc())" + CRLF,
        "                .order_by(ProfileExperience.start_date.asc())" + CRLF,
    ),
    # save_skills: строка без имени всё равно записывается
    (
        "backend/repository.py",
        "        if not name:" + CRLF
        + "            continue" + CRLF
        + '        category = (row.get("category") or "Общее").strip() or "Общее"',
        '        category = (row.get("category") or "Общее").strip() or "Общее"',
    ),
    # save_skills: пустой раздел перестаёт заменяться умолчанием
    (
        "backend/repository.py",
        '        category = (row.get("category") or "Общее").strip() or "Общее"',
        '        category = (row.get("category") or "Общее").strip()',
    ),
    # save_skills: мусорный уровень роняет сохранение
    (
        "backend/repository.py",
        "        except (TypeError, ValueError):" + CRLF + "            level = 1" + CRLF,
        "        except KeyError:" + CRLF + "            level = 1" + CRLF,
    ),
    # save_skills: среди написаний остаются пустые и не-строки
    (
        "backend/repository.py",
        "            if isinstance(a, str) and a.strip()" + CRLF,
        "            if True" + CRLF,
    ),
    # save_skills: строка с номером пересоздаётся вместо правки
    (
        "backend/repository.py",
        "        if rid_int is not None and rid_int in existing:",
        "        if False:",
    ),
    # save_skills: связи удаляемого навыка остаются висеть
    (
        "backend/repository.py",
        "        await session.execute(" + CRLF
        + "            delete(profile_experience_skills).where(" + CRLF
        + "                profile_experience_skills.c.skill_id == sid" + CRLF
        + "            )" + CRLF
        + "        )" + CRLF,
        "",
    ),
    # save_skills: неназванные строки перестают удаляться
    (
        "backend/repository.py",
        "    drop_ids = set(existing.keys()) - keep_ids",
        "    drop_ids = set()",
    ),
    # save_experience: пустая компания перестаёт отвергаться
    (
        "backend/repository.py",
        "        if not company:" + CRLF
        + '            raise SaveExperienceError(i, "не заполнено название компании")' + CRLF,
        "",
    ),
    # save_experience: пустая должность перестаёт отвергаться
    (
        "backend/repository.py",
        "        if not role:" + CRLF
        + '            raise SaveExperienceError(i, "не заполнена должность")' + CRLF,
        "",
    ),
    # save_experience: пустая дата начала перестаёт отвергаться
    (
        "backend/repository.py",
        "        if not start_iso:" + CRLF
        + '            raise SaveExperienceError(i, "не заполнена дата начала")' + CRLF,
        "",
    ),
    # save_experience: неверная дата окончания проходит как пустая
    (
        "backend/repository.py",
        "                raise SaveExperienceError(" + CRLF
        + '                    i, f"неверная дата окончания: {end_iso!r}"' + CRLF
        + "                )" + CRLF,
        "                end_date = None" + CRLF,
    ),
    # save_experience: номер неверной строки считается с нуля
    (
        "backend/repository.py",
        "    for i, row in enumerate(rows, start=1):",
        "    for i, row in enumerate(rows):",
    ),
    # save_experience: прежние места не стираются перед записью
    (
        "backend/repository.py",
        "    await session.execute(delete(ProfileExperience))" + CRLF
        + "    await session.flush()" + CRLF,
        "    await session.flush()" + CRLF,
    ),
    # save_experience: пустая ссылка на компанию сохраняется пустой строкой
    (
        "backend/repository.py",
        '        company_url = (row.get("company_url") or "").strip() or None',
        '        company_url = (row.get("company_url") or "").strip()',
    ),
    # save_experience: в достижения попадают пустые и не-строки
    (
        "backend/repository.py",
        '                a for a in (row.get("achievements") or []) if isinstance(a, str) and a.strip()',
        '                a for a in (row.get("achievements") or [])',
    ),
    # save_experience: сопоставление навыка начинает различать регистр
    (
        "backend/repository.py",
        "            s = skills_by_name.get(str(sname).lower())",
        "            s = skills_by_name.get(str(sname))",
    ),
    # save_experience: неизвестный навык роняет сохранение
    (
        "backend/repository.py",
        "            if s is not None:" + CRLF + "                exp.skills.append(s)" + CRLF,
        "            exp.skills.append(s)" + CRLF,
    ),
    # upsert_profile: правка заводит вторую строку вместо изменения первой
    (
        "backend/repository.py",
        "    if profile is None:" + CRLF + "        profile = Profile(**fields)",
        "    if True:" + CRLF + "        profile = Profile(**fields)",
    ),
    # list_profile_languages: порядок заведения теряется
    (
        "backend/repository.py",
        "        select(ProfileLanguage).order_by(ProfileLanguage.id)",
        "        select(ProfileLanguage).order_by(ProfileLanguage.language)",
    ),
    # replace_profile_languages: прежние языки не стираются
    (
        "backend/repository.py",
        "    await session.execute(" + CRLF
        + "        delete(ProfileLanguage).where(" + CRLF
        + "            ProfileLanguage.profile_id == profile_id" + CRLF
        + "        )" + CRLF
        + "    )" + CRLF,
        "",
    ),
    # save_parsed_cv: прежние языки переживают запись
    (
        "backend/repository.py",
        "    await session.execute(delete(ProfileLanguage))" + CRLF,
        "",
    ),
    # save_parsed_cv: прежние связи переживают запись
    (
        "backend/repository.py",
        "    await session.execute(delete(profile_experience_skills))" + CRLF
        + "    await session.execute(delete(ProfileExperience))" + CRLF
        + "    await session.execute(delete(ProfileSkill))" + CRLF,
        "    await session.execute(delete(ProfileExperience))" + CRLF
        + "    await session.execute(delete(ProfileSkill))" + CRLF,
    ),
    # save_parsed_cv: написания навыка перестают участвовать в сопоставлении
    (
        "backend/repository.py",
        "        for key_src in (s.name, *s.aliases):",
        "        for key_src in (s.name,):",
    ),
    # save_parsed_cv: путь к файлу резюме не сохраняется
    (
        "backend/repository.py",
        "    if cv_path is not None:" + CRLF,
        "    if False:" + CRLF,
    ),
    # save_parsed_cv: прежний путь к файлу задваивается
    (
        "backend/repository.py",
        "        if existing is None:" + CRLF
        + '            session.add(AppSetting(key="cv_path", value=cv_path))' + CRLF,
        "        if True:" + CRLF
        + '            session.add(AppSetting(key="cv_path", value=cv_path))' + CRLF,
    ),
    # build_profile_block: незаполненная роль называется пустотой
    (
        "backend/repository.py",
        "    if profile.title:" + CRLF
        + '        header_lines.append(f"Роль: {profile.title}")' + CRLF,
        '    header_lines.append(f"Роль: {profile.title}")' + CRLF,
    ),
    # build_profile_block: незаполненная локация называется пустотой
    (
        "backend/repository.py",
        "    if profile.location:" + CRLF
        + '        header_lines.append(f"Локация: {profile.location}")' + CRLF,
        '    header_lines.append(f"Локация: {profile.location}")' + CRLF,
    ),
    # build_profile_block: годы опыта считаются от самого позднего места
    (
        "backend/repository.py",
        "        min_start = min(e.start_date for e in experiences)",
        "        min_start = max(e.start_date for e in experiences)",
    ),
    # build_profile_block: у текущего места вместо срока пустота
    (
        "backend/repository.py",
        '        end = e.end_date.strftime("%m.%Y") if e.end_date else "настоящее время"',
        '        end = e.end_date.strftime("%m.%Y") if e.end_date else ""',
    ),
    # build_profile_block: к месту приписывается последнее достижение
    (
        "backend/repository.py",
        '        suffix = f": {e.achievements[0]}" if e.achievements else ""',
        '        suffix = f": {e.achievements[-1]}" if e.achievements else ""',
    ),
    # build_profile_block: пожелания уходят в запрос всегда
    (
        "backend/repository.py",
        "    if profile.free_preferences:" + CRLF,
        "    if profile.free_preferences is not None or True:" + CRLF,
    ),
    # build_profile_block: без профиля возвращается не пустая строка
    (
        "backend/repository.py",
        "    if profile is None:" + CRLF + '        return ""' + CRLF,
        "",
    ),
]
