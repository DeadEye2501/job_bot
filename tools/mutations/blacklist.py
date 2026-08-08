"""Поломки для `backend/repository/blacklist.py`.

Где поломка захватывает конец строки, перевод пишется через `CRLF`: рабочее
дерево здесь с виндовыми переводами, и поиск по `\\n` не находит ничего.
"""

CRLF = "\r\n"

MUTATIONS = [
    # set_blacklist_active: переключение не доходит до строки
    (
        "backend/repository/blacklist.py",
        "    row.active = bool(active)" + CRLF,
        "",
    ),
    # update_blacklist: пустое значение перестаёт отвергаться
    (
        "backend/repository/blacklist.py",
        '            raise BlacklistUpdateError("Значение не может быть пустым.")' + CRLF
        + "        row.value = normalized_value" + CRLF,
        "        row.value = normalized_value" + CRLF,
    ),
    # update_blacklist: правка причины трогает и значение
    (
        "backend/repository/blacklist.py",
        "    if reason is not _BLACKLIST_FIELD_UNSET:" + CRLF,
        "    if True:" + CRLF,
    ),
    # update_blacklist: пустая причина сохраняется пустой строкой
    (
        "backend/repository/blacklist.py",
        "        row.reason = normalized_reason or None",
        "        row.reason = normalized_reason",
    ),
    # create_blacklist: пустое значение перестаёт отвергаться
    (
        "backend/repository/blacklist.py",
        "    if not normalized_value:" + CRLF
        + '        raise BlacklistUpdateError("Значение не может быть пустым.")' + CRLF,
        "",
    ),
    # create_blacklist: пустой род перестаёт отвергаться
    (
        "backend/repository/blacklist.py",
        "    if not normalized_kind:" + CRLF
        + '        raise BlacklistUpdateError("Тип обязателен.")' + CRLF,
        "",
    ),
    # create_blacklist: сведение повторов идёт по одному значению, без рода
    (
        "backend/repository/blacklist.py",
        "                Blacklist.kind == normalized_kind," + CRLF
        + "                Blacklist.value == normalized_value," + CRLF,
        "                Blacklist.value == normalized_value," + CRLF,
    ),
    # create_blacklist: погашенная строка не оживает
    (
        "backend/repository/blacklist.py",
        "        if not existing.active:" + CRLF + "            existing.active = True" + CRLF,
        "        if False:" + CRLF + "            existing.active = True" + CRLF,
    ),
    # create_blacklist: новая причина затирает прежнюю
    (
        "backend/repository/blacklist.py",
        "        if normalized_reason and not existing.reason:",
        "        if normalized_reason:",
    ),
    # create_blacklist: повтор сообщается как заведение
    (
        "backend/repository/blacklist.py",
        "        return existing, False",
        "        return existing, True",
    ),
    # create_blacklist: новая строка заводится погашенной
    (
        "backend/repository/blacklist.py",
        "        reason=normalized_reason," + CRLF + "        active=True," + CRLF,
        "        reason=normalized_reason," + CRLF + "        active=False," + CRLF,
    ),
    # delete_blacklist: строка не удаляется
    (
        "backend/repository/blacklist.py",
        "    await session.delete(row)" + CRLF + "    return True" + CRLF + CRLF + CRLF
        + "async def list_blacklist_candidates(",
        "    return True" + CRLF + CRLF + CRLF + "async def list_blacklist_candidates(",
    ),
    # list_blacklist: порядок перестаёт быть устойчивым
    (
        "backend/repository/blacklist.py",
        "            select(Blacklist).order_by(Blacklist.id.asc())",
        "            select(Blacklist).order_by(Blacklist.active.desc())",
    ),
    # load_active_blacklist_patterns: погашенные значения снова отсеивают
    (
        "backend/repository/blacklist.py",
        "                select(Blacklist.value).where(Blacklist.active)",
        "                select(Blacklist.value)",
    ),
    # list_blacklist_candidates: HR без признаков попадает в подсказки
    (
        "backend/repository/blacklist.py",
        "            if value is None:" + CRLF + "                continue" + CRLF
        + "            label = hr.name or value",
        "            label = hr.name or value",
    ),
    # list_blacklist_candidates: у именованного HR пропадает подпись
    (
        "backend/repository/blacklist.py",
        "            sub = value if hr.name else None" + CRLF,
        "            sub = None" + CRLF,
    ),
    # list_blacklist_candidates: порядок людей перестаёт игнорировать регистр
    (
        "backend/repository/blacklist.py",
        '        out.sort(key=lambda x: (x["label"] or "").casefold())' + CRLF
        + "        return out" + CRLF
        + '    if kind == "company":',
        '        out.sort(key=lambda x: (x["label"] or ""))' + CRLF
        + "        return out" + CRLF
        + '    if kind == "company":',
    ),
    # list_blacklist_candidates: компании перестают упорядочиваться
    (
        "backend/repository/blacklist.py",
        "            await session.scalars(select(Company).order_by(Company.name.asc()))",
        "            await session.scalars(select(Company))",
    ),
    # list_blacklist_candidates: порядок каналов перестаёт игнорировать регистр
    (
        "backend/repository/blacklist.py",
        '        out.sort(key=lambda x: (x["label"] or "").casefold())' + CRLF
        + "        return out" + CRLF
        + "    return []",
        '        out.sort(key=lambda x: (x["label"] or ""))' + CRLF
        + "        return out" + CRLF
        + "    return []",
    ),
    # list_blacklist_candidates: незнакомый род начинает отдавать людей
    (
        "backend/repository/blacklist.py",
        '    if kind == "hr":' + CRLF,
        "    if True:" + CRLF,
    ),
]
