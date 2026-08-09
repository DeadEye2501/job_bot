"""Поломки для `backend/repository/blacklist_marks.py`.

Набор собран из трёх: до сведения отметка искалась тремя одинаковыми запросами
в `hr_card`, `companies_card` и `channels`, и у каждого была своя копия цели.
Место осталось одно — значит и цель одна, но прогонять её надо против тестов
всех трёх предметов сразу, иначе проверено будет меньше прежнего.

Где поломка захватывает конец строки, перевод пишется через `CRLF`: рабочее
дерево здесь с виндовыми переводами, и поиск по `\\n` не находит ничего.
"""

CRLF = "\r\n"

MUTATIONS = [
    # active_blacklist_value: выключенные отметки снова видны
    (
        "backend/repository/blacklist_marks.py",
        "                Blacklist.kind == kind," + CRLF
        + "                Blacklist.value.in_(candidates)," + CRLF
        + "                Blacklist.active.is_(True)," + CRLF,
        "                Blacklist.kind == kind," + CRLF
        + "                Blacklist.value.in_(candidates)," + CRLF,
    ),
    # active_blacklist_value: отметка находится под чужим родом
    (
        "backend/repository/blacklist_marks.py",
        "                Blacklist.kind == kind," + CRLF
        + "                Blacklist.value.in_(candidates)," + CRLF
        + "                Blacklist.active.is_(True)," + CRLF
        + "            )" + CRLF
        + "            .order_by(Blacklist.id.asc())",
        "                Blacklist.value.in_(candidates)," + CRLF
        + "                Blacklist.active.is_(True)," + CRLF
        + "            )" + CRLF
        + "            .order_by(Blacklist.id.asc())",
    ),
    # active_blacklist_value: при двух написаниях побеждает заведённое позже
    (
        "backend/repository/blacklist_marks.py",
        "            .order_by(Blacklist.id.asc())",
        "            .order_by(Blacklist.id.desc())",
    ),
    # active_blacklist_values: погашенные значения снова отсеивают
    (
        "backend/repository/blacklist_marks.py",
        "                    Blacklist.kind == kind," + CRLF
        + "                    Blacklist.active.is_(True)," + CRLF,
        "                    Blacklist.kind == kind," + CRLF,
    ),
    # active_blacklist_values: перечень получает значения чужого рода
    (
        "backend/repository/blacklist_marks.py",
        "                    Blacklist.kind == kind," + CRLF
        + "                    Blacklist.active.is_(True)," + CRLF,
        "                    Blacklist.active.is_(True)," + CRLF,
    ),
]
