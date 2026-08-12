"""Следствия, которые наблюдают тесты журналирования.

Трое соседей по слою: кольцо записей для окна (`log_buffer`), вымарывание
секретов вместе с жалобой на свою беду (`log_secrets`) и файл журнала
(`log_file`).

Корневой logger — общее состояние процесса: каждый тест, который его трогает,
возвращает как было, иначе следующий тест видит чужие обработчики.
"""

import logging
import os
import sys

import pytest

from config import get_log_path

from backend.log_buffer import MAX_RECORDS, LogBufferHandler, install
from backend.log_file import LogFileHandler
from backend.log_secrets import SecretRedactionFilter, install_secret_filter


@pytest.fixture
def clean_log_file():
    """Пустой файл журнала на входе в тест и убранный на выходе.

    В него обработчик буфера сообщает о своих бедах, минуя логирование.
    Остаток от прошлого теста подменял бы «записалось сейчас» на «лежало
    и раньше».
    """
    path = get_log_path()
    path.unlink(missing_ok=True)
    yield path
    path.unlink(missing_ok=True)


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
    """Повторная установка не добавляет второй фильтр — и никого не обходит.

    Обработчиков двое нарочно, и считается фильтр у каждого по отдельности:
    по общему числу «два на одном и ноль на другом» неотличимо от «по одному
    на каждом», а это и есть беда — необойдённый обработчик пишет секрет как
    есть.
    """
    ours = [LogBufferHandler(), logging.StreamHandler()]
    for handler in ours:
        clean_root_logger.addHandler(handler)
    install_secret_filter()
    install_secret_filter()

    per_handler = [
        sum(isinstance(f, SecretRedactionFilter) for f in handler.filters)
        for handler in ours
    ]
    assert per_handler == [1, 1]


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


def test_an_unrenderable_traceback_does_not_reach_the_caller(clean_log_file):
    """Неотрисовываемая трассировка не выходит наружу к зовущему.

    Фильтр работает до защитного перехвата вокруг записи: своё падение здесь
    ушло бы тому, кто просто позвал `logger.exception` внутри своего `except`,
    и жалоба на беду стала бы второй бедой. Собрать трассировку в таком
    случае остаётся форматтеру — он-то как раз под защитой.
    """
    entry = record("запрос не прошёл")
    entry.exc_info = (ValueError, "не исключение", None)

    assert SecretRedactionFilter().filter(entry) is True
    assert entry.exc_text is None


def test_a_secret_in_a_traceback_is_masked_too(clean_root_logger, clean_log_file):
    """Секрет из трассировки вымарывается наравне с секретом из сообщения.

    Трассировку собирает форматтер, а он работает уже внутри обработчика —
    то есть после фильтров. Достаётся это первому обработчику по списку: он
    заполняет трассировку в самой записи, и следующим она приходит уже
    собранной. В бою первый — файловый, и секрет из текста исключения
    третьей библиотеки лёг бы в файл как есть.
    """
    handler = LogFileHandler(clean_log_file, encoding="utf-8", delay=True)
    clean_root_logger.handlers.insert(0, handler)
    install_secret_filter()

    try:
        raise RuntimeError("токен Bearer abcdefgh12345678")
    except RuntimeError:
        logging.getLogger("httpx.child").exception("запрос не прошёл")
    handler.close()

    assert "abcdefgh12345678" not in clean_log_file.read_text(encoding="utf-8")


def _busy(source, dest):
    """Отказ ОС переименовать файл, открытый другим процессом."""
    raise PermissionError(32, "файл занят другим процессом")


def test_a_rotation_into_a_busy_file_does_not_silence_the_handler(
    clean_log_file, monkeypatch
):
    """Ротация, упёршаяся в занятый файл, обработчика не выключает.

    Переименовать открытый файл Windows не даёт, а открыт он бывает у
    второй копии приложения — базу они делят и сегодня. Штатный переход
    оставляет поток закрытым, и каждая следующая запись упирается в ту же
    ротацию: журнал замолкает до перезапуска, то есть теряется ровно та
    история, ради которой он заведён.
    """
    handler = LogFileHandler(
        clean_log_file, encoding="utf-8", maxBytes=1, backupCount=1
    )
    monkeypatch.setattr(os, "rename", _busy)

    handler.emit(record("до поворота"))
    handler.emit(record("после поворота"))
    handler.close()

    lines = clean_log_file.read_text(encoding="utf-8").splitlines()
    assert "после поворота" in lines
    assert any("не повернуть" in line for line in lines)


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


def test_a_failing_subscriber_is_reported_and_not_swallowed(clean_log_file):
    """Об упавшем подписчике сообщается, а не молчится.

    Записать беду обычным путём тут нельзя — это сам обработчик логов, и
    запись из него ушла бы по кругу. Штатный для такого `handleError`
    печатает в поток ошибок, а в оконной сборке его нет вовсе — поэтому
    сообщается прямо в файл журнала, мимо логирования.
    """
    handler = LogBufferHandler()

    def failing_subscriber(entry):
        raise RuntimeError("подписчик сломался")

    handler.on_record = failing_subscriber

    handler.emit(record("сообщение"))

    assert "подписчик сломался" in clean_log_file.read_text(encoding="utf-8")


def _unbuildable():
    """Запись, у которой сообщение не собирается: доводов меньше, чем мест."""
    return logging.LogRecord(
        name="проверка", level=logging.ERROR, pathname=__file__, lineno=1,
        msg="не хватает %s и %s", args=("одного",), exc_info=None,
    )


def test_a_record_that_cannot_be_built_leaves_a_trace_from_the_filter(
    clean_log_file,
):
    """Неразбираемая запись оставляет след, а не проходит фильтр молча.

    Собрать сообщение фильтр не смог — значит и вымарать секреты в нём не
    смог. Пропустить такую запись дальше можно, промолчать о ней нельзя:
    именно в ней секрет и уедет незамаскированным.
    """
    assert SecretRedactionFilter().filter(_unbuildable()) is True

    assert "не хватает" in clean_log_file.read_text(encoding="utf-8")


def test_a_record_that_cannot_be_built_leaves_a_trace_from_the_handler(
    clean_log_file,
):
    """Та же запись оставляет след и в обработчике буфера."""
    handler = LogBufferHandler()

    handler.emit(_unbuildable())

    assert handler.snapshot()[-1]["msg"] == "не хватает %s и %s"
    assert "не хватает" in clean_log_file.read_text(encoding="utf-8")


def test_an_unformattable_traceback_leaves_a_trace(clean_log_file):
    """Несобравшаяся трассировка оставляет след, а не тихо теряется."""
    handler = LogBufferHandler()

    class Refuses(logging.Formatter):
        def format(self, record):
            raise RuntimeError(f"форматтер сломался на {record.name}")

    handler.setFormatter(Refuses())
    try:
        raise ValueError("сломалось")
    except ValueError:
        entry = logging.LogRecord(
            name="проверка", level=logging.ERROR, pathname=__file__, lineno=1,
            msg="упало", args=(), exc_info=sys.exc_info(),
        )
    handler.emit(entry)

    assert handler.snapshot()[-1]["details"] is None
    assert "форматтер сломался" in clean_log_file.read_text(encoding="utf-8")


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


def test_a_secret_in_an_unreadable_template_is_masked_in_the_file(clean_log_file):
    """Секрет из несобравшейся записи не уезжает в файл открытым.

    Вымарывать её обычным путём нечем — сообщение не собралось, — но именно
    поэтому шаблон и попадает в отчёт целиком, а в шаблоне бывает всё.
    """
    entry = logging.LogRecord(
        name="проверка", level=logging.ERROR, pathname=__file__, lineno=1,
        msg="токен Bearer abcdefgh12345678 и %s и %s", args=("одного",), exc_info=None,
    )

    SecretRedactionFilter().filter(entry)

    written = clean_log_file.read_text(encoding="utf-8")
    assert "abcdefgh12345678" not in written
    assert "***" in written


def test_one_bad_record_is_reported_once_by_the_filter(clean_log_file):
    """Одна негодная запись — один отчёт от фильтра, сколько бы их ни висело.

    Фильтр вешается на каждый обработчик корня своим экземпляром, и без
    отметки на записи о ней сообщил бы каждый: три обработчика — три
    трассировки. Поток таких записей вытер бы историю, ради которой файл и
    заведён.
    """
    entry = _unbuildable()

    SecretRedactionFilter().filter(entry)
    SecretRedactionFilter().filter(entry)
    SecretRedactionFilter().filter(entry)

    assert clean_log_file.read_text(encoding="utf-8").count("не собирается") == 1


def test_a_template_that_cannot_be_read_does_not_break_the_caller():
    """Логирование не роняет того, кто его позвал, даже на дикой записи.

    Шаблон записи бывает не строкой, а объектом, и его `__repr__` тоже
    бывает сломан. Раньше такая запись проходила фильтр молча; теперь о ней
    сообщают — и это не должно превратить жалобу в падение.
    """

    class Wild:
        def __repr__(self):
            raise RuntimeError("шаблон не читается")

    entry = logging.LogRecord(
        name="проверка", level=logging.ERROR, pathname=__file__, lineno=1,
        msg=Wild(), args=("лишний",), exc_info=None,
    )

    assert SecretRedactionFilter().filter(entry) is True


def test_an_unavailable_file_is_reported_to_the_stream(monkeypatch, capsys, tmp_path):
    """Когда и файл недоступен, беда уходит в поток ошибок."""
    monkeypatch.setattr("backend.log_secrets.get_log_path", lambda: tmp_path)

    LogBufferHandler().emit(_unbuildable())

    said = capsys.readouterr().err
    assert "не собирается" in said
    assert "Traceback" in said


def test_nothing_blows_up_when_there_is_nowhere_to_complain(
    monkeypatch, tmp_path
):
    """Когда некуда сказать вовсе, логирование всё равно не падает.

    Каталог на месте файла плюс оконная сборка, где потока ошибок нет: это
    последний рубеж, и дальше него жаловаться правда некуда.
    """
    monkeypatch.setattr("backend.log_secrets.get_log_path", lambda: tmp_path)
    monkeypatch.setattr(sys, "stderr", None)

    LogBufferHandler().emit(_unbuildable())
