"""Следствия, которые наблюдают тесты `backend/log_buffer.py`.

Корневой logger — общее состояние процесса: каждый тест, который его трогает,
возвращает как было, иначе следующий тест видит чужие обработчики.
"""

import logging

import pytest

from backend.log_buffer import (
    MAX_RECORDS,
    LogBufferHandler,
    SecretRedactionFilter,
    install,
    install_secret_filter,
)


def record(msg: str, *, name: str = "проверка", level: int = logging.INFO):
    """Готовая запись журнала для подачи в фильтр или обработчик."""
    return logging.LogRecord(
        name=name, level=level, pathname=__file__, lineno=1,
        msg=msg, args=(), exc_info=None,
    )


@pytest.mark.parametrize(
    "raw",
    [
        "Authorization: Bearer abcdefgh12345678",
        "ключ sk-abcdefghijklmnop0123",
        "api_hash='9cc8ccb459f977b52c89b3199fa8e591'",
        "сессия " + "A" * 60,
    ],
)
def test_a_secret_never_reaches_the_record(raw):
    """Секрет не доезжает до записи: на его месте затирка."""
    entry = record(raw)

    SecretRedactionFilter().filter(entry)

    assert "***" in entry.msg
    assert raw not in entry.msg


def test_a_short_token_is_not_mistaken_for_a_secret():
    """Короткая строка за секрет не принимается."""
    entry = record("идентификатор abc123")

    SecretRedactionFilter().filter(entry)

    assert entry.msg == "идентификатор abc123"


def test_redaction_keeps_a_record_with_args_readable():
    """Затирка секрета не ломает запись, собираемую из аргументов."""
    entry = logging.LogRecord(
        name="проверка", level=logging.INFO, pathname=__file__, lineno=1,
        msg="токен %s", args=("Bearer abcdefgh12345678",), exc_info=None,
    )

    SecretRedactionFilter().filter(entry)

    assert "***" in entry.getMessage()


def test_installing_the_filter_twice_adds_it_once(clean_root_logger):
    """Повторная установка не добавляет второй фильтр."""
    clean_root_logger.addHandler(LogBufferHandler())
    install_secret_filter()
    install_secret_filter()

    installed = [
        f
        for handler in clean_root_logger.handlers
        for f in handler.filters
        if isinstance(f, SecretRedactionFilter)
    ]
    assert len(installed) == len(clean_root_logger.handlers)


def test_a_secret_from_someone_elses_logger_is_masked_too(clean_root_logger):
    """Секрет из записи чужого logger'а вымарывается наравне со своим.

    Фильтр на logger'е видит только записи, сделанные им самим: до
    обработчиков предка запись доходит мимо его фильтров. А записи третьих
    библиотек — httpx, pyrogram, sqlalchemy — идут именно так, и ради них
    фильтр и заведён.
    """
    handler = LogBufferHandler()
    clean_root_logger.addHandler(handler)
    install_secret_filter()

    logging.getLogger("httpx.child").warning("токен Bearer abcdefgh12345678")

    assert "abcdefgh12345678" not in handler.snapshot()[-1]["msg"]


def test_a_record_lands_in_the_snapshot_with_level_and_source():
    """Запись попадает в срез с уровнем и источником."""
    handler = LogBufferHandler()

    handler.emit(record("сообщение", name="backend.проверка", level=logging.WARNING))

    entry = handler.snapshot()[-1]
    assert entry["msg"] == "сообщение"
    assert entry["level"] == "WARNING"
    assert entry["source"] == "backend.проверка"


def test_records_are_numbered_consecutively():
    """Записи нумеруются подряд, номер не повторяется."""
    handler = LogBufferHandler()

    handler.emit(record("первая"))
    handler.emit(record("вторая"))

    assert [e["id"] for e in handler.snapshot()] == [1, 2]


def test_the_ring_stays_bounded_and_drops_the_oldest():
    """Кольцо не растёт за предел и теряет самые старые записи."""
    handler = LogBufferHandler()

    for i in range(MAX_RECORDS + 10):
        handler.emit(record(f"запись {i}"))

    snapshot = handler.snapshot()
    assert len(snapshot) == MAX_RECORDS
    assert snapshot[0]["msg"] == "запись 10"


def test_clearing_returns_the_count_and_empties_the_buffer():
    """Очистка возвращает число убранного и опустошает буфер."""
    handler = LogBufferHandler()
    handler.emit(record("одна"))
    handler.emit(record("вторая"))

    assert handler.clear() == 2
    assert handler.snapshot() == []


def test_the_subscriber_receives_every_record():
    """Подписчик получает каждую запись."""
    handler = LogBufferHandler()
    seen: list[dict] = []
    handler.on_record = seen.append

    handler.emit(record("сообщение"))

    assert [e["msg"] for e in seen] == ["сообщение"]


def test_a_failing_subscriber_does_not_stop_buffering():
    """Упавший подписчик не мешает записи попасть в буфер."""
    handler = LogBufferHandler()

    def failing_subscriber(entry):
        raise RuntimeError("подписчик сломался")

    handler.on_record = failing_subscriber

    handler.emit(record("сообщение"))

    assert handler.snapshot()[-1]["msg"] == "сообщение"


def test_a_failing_subscriber_is_reported_and_not_swallowed(capsys):
    """Об упавшем подписчике сообщается, а не молчится.

    Записать беду обычным путём тут нельзя — это сам обработчик логов, и
    запись из него ушла бы по кругу. Для такого у стандартной библиотеки
    заведён `handleError`: он печатает трассировку в поток ошибок.
    """
    handler = LogBufferHandler()

    def failing_subscriber(entry):
        raise RuntimeError("подписчик сломался")

    handler.on_record = failing_subscriber

    handler.emit(record("сообщение"))

    assert "подписчик сломался" in capsys.readouterr().err


def test_a_traceback_lands_in_the_details():
    """Трассировка попадает в подробности записи."""
    import sys

    handler = LogBufferHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    try:
        raise ValueError("сломалось")
    except ValueError:
        entry = logging.LogRecord(
            name="проверка", level=logging.ERROR, pathname=__file__, lineno=1,
            msg="упало", args=(), exc_info=sys.exc_info(),
        )
        handler.emit(entry)

    assert "ValueError: сломалось" in handler.snapshot()[-1]["details"]


def test_a_record_without_an_exception_has_no_details():
    """У записи без исключения подробностей нет."""
    handler = LogBufferHandler()

    handler.emit(record("сообщение"))

    assert handler.snapshot()[-1]["details"] is None


def test_install_attaches_the_handler_and_lets_debug_through(clean_root_logger):
    """Установка вешает обработчик и пропускает отладочные записи."""
    clean_root_logger.setLevel(logging.INFO)

    handler = install()
    logging.getLogger("backend.проверка").debug("отладочное")

    assert handler in clean_root_logger.handlers
    assert handler.snapshot()[-1]["msg"] == "отладочное"


def test_installing_twice_attaches_one_handler(clean_root_logger):
    """Повторная установка не вешает второй обработчик."""
    from backend.log_buffer import get_handler

    install()
    install()

    assert clean_root_logger.handlers.count(get_handler()) == 1
