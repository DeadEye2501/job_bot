"""Поломки для `backend/runtime_settings.py`.

Где поломка захватывает конец строки, перевод пишется через `CRLF`: рабочее
дерево здесь с виндовыми переводами, и поиск по `\\n` не находит ничего.
"""

CRLF = "\r\n"

MUTATIONS = [
    # _app_int: негодное значение снова роняет чтение
    (
        "backend/runtime_settings.py",
        "        try:" + CRLF
        + "            return int(raw)" + CRLF
        + "        except ValueError:",
        "        if True:" + CRLF
        + "            return int(raw)" + CRLF
        + "        if False:",
    ),
    # _app_int: откат идёт не к объявленному умолчанию
    (
        "backend/runtime_settings.py",
        "            return int(_APP_DEFAULTS[key])",
        "            return 0",
    ),
]
