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
    # chat: отказ провайдера перестаёт быть отказом
    (
        "adapters/lm_studio.py",
        '        r = await client.post("/v1/chat/completions", json=body, **extra)'
        + CRLF
        + "        r.raise_for_status()",
        '        r = await client.post("/v1/chat/completions", json=body, **extra)',
    ),
    # chat: своё время ожидания не доезжает до запроса
    (
        "adapters/lm_studio.py",
        '    extra = {} if request.timeout is None else {"timeout": request.timeout}',
        "    extra = {}",
    ),
    # chat: признак завершения теряется по дороге
    (
        "adapters/lm_studio.py",
        "    return ChatAnswer(text=content.strip(), finish_reason=finish_reason)",
        "    return ChatAnswer(text=content.strip())",
    ),
    # chat: неразбираемый ответ отдаётся как пустой, без причины
    (
        "adapters/lm_studio.py",
        '        return ChatAnswer(error=f"malformed_response: {e}")',
        "        return ChatAnswer()",
    ),
]
