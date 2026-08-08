"""Поломки для входных точек: соединение с базой, клиент Telegram, запуск.

Переводы строк здесь юниксовые, в отличие от файлов `backend/`: эти легли в
дерево с `\\n`. Поиск по `\\r\\n` в них не находит ничего — проверено проходом,
где двенадцать поломок из двадцати не совпали.
"""

CRLF = "\n"

MUTATIONS = [
    # make_engine: внешние ключи перестают стеречься
    (
        "adapters/db.py",
        '            cursor.execute("PRAGMA foreign_keys=ON")' + CRLF,
        "",
    ),
    # make_engine: журнал остаётся в режиме, где читатель ждёт писателя
    (
        "adapters/db.py",
        '            cursor.execute("PRAGMA journal_mode=WAL")' + CRLF,
        "",
    ),
    # make_engine: занятую базу перестают ждать
    (
        "adapters/db.py",
        '            cursor.execute("PRAGMA busy_timeout=5000")' + CRLF,
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
        "            in_memory=True," + CRLF,
        "            in_memory=False," + CRLF,
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
        "            in_memory=True," + CRLF + "            sleep_threshold=60," + CRLF,
        "            in_memory=True," + CRLF,
    ),
    # make_client: сохранённая сессия не используется вовсе
    (
        "adapters/telegram.py",
        "    if tg.session_string:" + CRLF,
        "    if False:" + CRLF,
    ),
    # send_dm: запор отправки снимается
    (
        "adapters/telegram.py",
        "    if SEND_LOCKED:" + CRLF,
        "    if False:" + CRLF,
    ),
    # send_dm: заглушенная отправка выдаёт номер, будто письмо ушло
    (
        "adapters/telegram.py",
        '            len(text),' + CRLF + "        )" + CRLF + "        return None" + CRLF,
        '            len(text),' + CRLF + "        )" + CRLF + "        return 0" + CRLF,
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
        "    if attachment is not None:" + CRLF,
        "    if False:" + CRLF,
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
        '    cfg.set_main_option("sqlalchemy.url", get_database_url())' + CRLF,
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
