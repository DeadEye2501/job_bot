"""Поломки для входных точек: соединение с базой, клиент Telegram, запуск.

Переводы строк тут разные, и это не мелочь: `adapters/` и `bootstrap.py` легли
в дерево с `\\n`, а `main.py` — с `\\r\\n`. Поиск не той парой не находит ничего
и молчит об этом, поэтому констант две, и берётся та, что под файл.
"""

LF = "\n"
CRLF = "\r\n"

MUTATIONS = [
    # make_engine: кириллица в JSON-колонках снова экранируется.
    # Убийца лежит вне обычного круга этого набора —
    # tests/backend/test_repository_vacancy_joins.py, проверка про поиск по
    # стеку: форму хранения снаружи видно только через неё.
    (
        "adapters/db.py",
        "    return json.dumps(value, ensure_ascii=False)",
        "    return json.dumps(value)",
    ),
    # make_engine: внешние ключи перестают стеречься
    (
        "adapters/db.py",
        '            cursor.execute("PRAGMA foreign_keys=ON")' + LF,
        "",
    ),
    # make_engine: журнал остаётся в режиме, где читатель ждёт писателя
    (
        "adapters/db.py",
        '            cursor.execute("PRAGMA journal_mode=WAL")' + LF,
        "",
    ),
    # make_engine: занятую базу перестают ждать
    (
        "adapters/db.py",
        '            cursor.execute("PRAGMA busy_timeout=5000")' + LF,
        "",
    ),
    # make_engine: приведение к нижнему регистру снова знает только латиницу
    (
        "adapters/db.py",
        '        dbapi_conn.create_function("lower", 1, _lower, deterministic=True)' + LF,
        "",
    ),
    # make_engine: настройки ставятся один раз, а не на каждое соединение
    (
        "adapters/db.py",
        '    @event.listens_for(engine.sync_engine, "connect")',
        '    @event.listens_for(engine.sync_engine, "first_connect")',
    ),
    # check: проверка соединения перестаёт называть версию движка
    (
        "adapters/db.py",
        '    return f"SQLite {version}"',
        '    return "SQLite"',
    ),
    # make_client: сохранённая сессия перестаёт жить в памяти
    (
        "adapters/telegram.py",
        "            in_memory=True," + LF,
        "            in_memory=False," + LF,
    ),
    # make_client: пустой пароль второго шага уходит как заданный
    (
        "adapters/telegram.py",
        "        password=tg.password or None,",
        "        password=tg.password,",
    ),
    # make_client: короткие запреты частоты перестают пережидаться сами
    (
        "adapters/telegram.py",
        "            in_memory=True," + LF + "            sleep_threshold=60," + LF,
        "            in_memory=True," + LF,
    ),
    # make_client: сохранённая сессия не используется вовсе
    (
        "adapters/telegram.py",
        "    if tg.session_string:" + LF,
        "    if False:" + LF,
    ),
    # send_dm: запор отправки снимается
    (
        "adapters/telegram.py",
        "    if SEND_LOCKED:" + LF,
        "    if False:" + LF,
    ),
    # send_dm: заглушенная отправка выдаёт номер, будто письмо ушло
    (
        "adapters/telegram.py",
        '            len(text),' + LF + "        )" + LF + "        return None" + LF,
        '            len(text),' + LF + "        )" + LF + "        return 0" + LF,
    ),
    # send_dm: вложение уходит без текста-подписи
    (
        "adapters/telegram.py",
        "        msg = await client.send_document(user, str(attachment), caption=text)",
        "        msg = await client.send_document(user, str(attachment))",
    ),
    # send_dm: вложение теряется, уходит только текст
    (
        "adapters/telegram.py",
        "    if attachment is not None:" + LF,
        "    if False:" + LF,
    ),
    # send_dm: номер ушедшего сообщения не возвращается
    (
        "adapters/telegram.py",
        '    return getattr(msg, "id", None)',
        "    return None",
    ),
    # ensure_schema: миграции применяются не к той базе
    (
        "backend/bootstrap.py",
        '    cfg.set_main_option("sqlalchemy.url", get_database_url())' + LF,
        "",
    ),
    # ensure_schema: схема не доводится до последней ревизии
    (
        "backend/bootstrap.py",
        '    command.upgrade(cfg, "head")',
        '    command.upgrade(cfg, "base")',
    ),
    # ensure_schema: миграции ищутся от рабочего каталога, а не от проекта
    (
        "backend/bootstrap.py",
        '    cfg.set_main_option("script_location", str(_PROJECT_ROOT / "alembic"))',
        '    cfg.set_main_option("script_location", "alembic")',
    ),
    # main: перенастройка вывода перестаёт вызываться вовсе
    (
        "main.py",
        "_use_utf8_stdout()" + CRLF + CRLF + CRLF + "logging.basicConfig(",
        "logging.basicConfig(",
    ),
    # _use_utf8_stdout: отказ консоли снова проглатывается молча
    (
        "main.py",
        "        traceback.print_exc()",
        "        pass",
    ),
    # main: проверка хранилища ключей перестаёт останавливать запуск
    (
        "main.py",
        "        logger.critical(\"keyring pre-flight failed: %s\", e)" + CRLF
        + '        print(f"\\n[Job Bot] Не удалось запуститься: {e}\\n", file=sys.stderr)' + CRLF
        + "        return 2" + CRLF,
        "        logger.critical(\"keyring pre-flight failed: %s\", e)" + CRLF
        + '        print(f"\\n[Job Bot] Не удалось запуститься: {e}\\n", file=sys.stderr)' + CRLF,
    ),
    # main: схема готовится после окна, а не до
    (
        "main.py",
        "    bootstrap.ensure_schema()" + CRLF + "    return run_ui()",
        "    result = run_ui()" + CRLF
        + "    bootstrap.ensure_schema()" + CRLF
        + "    return result",
    ),
    # main: код возврата окна не передаётся наружу
    (
        "main.py",
        "    return run_ui()",
        "    run_ui()" + CRLF + "    return 0",
    ),
]
