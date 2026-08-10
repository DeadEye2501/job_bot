"""Поломки для `backend/repository/blacklist_marks.py`.

Набор собран из трёх: до сведения отметка искалась тремя одинаковыми запросами
в `hr_card`, `companies_card` и `channels`, и у каждого была своя копия цели.
Место осталось одно — значит и цель одна, но прогонять её надо против тестов
всех трёх предметов сразу, иначе проверено будет меньше прежнего.

Само условие «предмет отмечен» уехало в `active_mark_of` пунктом 2 плана
`2026-08-10-bridge-writes-and-mirrors`, и цели на него живут в наборе
`blacklist`: здесь остались только запросы вокруг него.

Где поломка захватывает конец строки, перевод пишется через `CRLF`: рабочее
дерево здесь с виндовыми переводами, и поиск по `\\n` не находит ничего.
"""

CRLF = "\r\n"

MUTATIONS = [
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
