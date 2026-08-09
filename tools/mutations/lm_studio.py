"""Поломки для клиента провайдера моделей `adapters/lm_studio.py`.

Свой набор, а не часть `entry_points`: убийцы этих поломок живут в
`tests/adapters/test_lm_studio.py`, и в выборку того набора этот файл не
входит — оттуда поломки прошли бы молча и засчитались бы пойманными.

Файл лёг в дерево с виндовыми переводами строк, поэтому поломки, задевающие
конец строки, пишутся через `CRLF`: поиск не той парой не находит ничего.
"""

CRLF = "\r\n"

MUTATIONS = [
    # check_chat: список моделей снова без трассировки
    (
        "adapters/lm_studio.py",
        '        _log.exception("провайдер не отдал список моделей для чата")' + CRLF,
        "",
    ),
    # check_chat: пробный запрос снова без трассировки
    (
        "adapters/lm_studio.py",
        '        _log.exception("пробный запрос к чат-модели %s не прошёл", model)' + CRLF,
        "",
    ),
    # check_embed: список моделей снова без трассировки
    (
        "adapters/lm_studio.py",
        '        _log.exception("провайдер не отдал список моделей для векторов")' + CRLF,
        "",
    ),
    # check_embed: пробный запрос снова без трассировки
    (
        "adapters/lm_studio.py",
        '        _log.exception("пробный запрос к модели векторов %s не прошёл", model)' + CRLF,
        "",
    ),
    # check_chat: сетевая беда пробного запроса перестаёт ловиться
    (
        "adapters/lm_studio.py",
        "    except httpx.HTTPError as e:" + CRLF
        + '        _log.exception("пробный запрос к чат-модели %s не прошёл", model)',
        "    except ValueError as e:" + CRLF
        + '        _log.exception("пробный запрос к чат-модели %s не прошёл", model)',
    ),
    # check_embed: сетевая беда пробного запроса перестаёт ловиться
    (
        "adapters/lm_studio.py",
        "    except httpx.HTTPError as e:" + CRLF
        + '        _log.exception("пробный запрос к модели векторов %s не прошёл", model)',
        "    except ValueError as e:" + CRLF
        + '        _log.exception("пробный запрос к модели векторов %s не прошёл", model)',
    ),
]
