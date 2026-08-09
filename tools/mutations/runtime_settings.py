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
        + "            value = int(raw)" + CRLF
        + "        except ValueError:" + CRLF
        + "            value = None",
        "        if True:" + CRLF
        + "            value = int(raw)" + CRLF
        + "        if False:" + CRLF
        + "            value = None",
    ),
    # _app_int: откат идёт не к объявленному умолчанию
    (
        "backend/runtime_settings.py",
        "            return int(_APP_DEFAULTS[key])",
        "            return 0",
    ),
    # _app_int: нижняя граница перестаёт проверяться
    (
        "backend/runtime_settings.py",
        "        if value is None or (minimum is not None and value < minimum):",
        "        if value is None:",
    ),
    # _app_int: граница становится включающей наоборот
    (
        "backend/runtime_settings.py",
        "        if value is None or (minimum is not None and value < minimum):",
        "        if value is None or (minimum is not None and value <= minimum):",
    ),
    # scoring_threshold: отрицательный порог перестаёт браться как есть
    (
        "backend/runtime_settings.py",
        '        return self._app_int("scoring_threshold")',
        '        return self._app_int("scoring_threshold", minimum=0)',
    ),
    # backfill_limit: нулевой предел выборки снова проходит
    (
        "backend/runtime_settings.py",
        '        return self._app_int("backfill_limit", minimum=1)',
        '        return self._app_int("backfill_limit", minimum=0)',
    ),
    # dm_backfill_limit: нулевой предел выборки снова проходит
    (
        "backend/runtime_settings.py",
        '        return self._app_int("dm_backfill_limit", minimum=1)',
        '        return self._app_int("dm_backfill_limit", minimum=0)',
    ),
    # poll_interval_sec: нулевой интервал снова проходит
    (
        "backend/runtime_settings.py",
        '        return self._app_int("poll_interval_sec", minimum=1)',
        '        return self._app_int("poll_interval_sec", minimum=0)',
    ),
]
