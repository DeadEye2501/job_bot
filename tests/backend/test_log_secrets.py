"""Следствия вымарывания секретов и жалобы журнала на собственную беду.

Дела два, и вместе они не по родству, а потому, что порознь ходят по кругу:
жалоба на сорванную запись обязана быть вымаранной — в сломавшейся записи лежит
ровно то, что вымарывают, — а вымарыванию, когда оно само сломается, надо
пожаловаться. Так они и живут: одним модулем (`backend/log_secrets.py`).

Соседи по слою — свои: кольцо записей смотрит `test_log_buffer.py`, файл
журнала — `test_log_file.py`.
"""

import logging
import sys

import pytest

from backend.log_buffer import LogBufferHandler
from backend.log_file import LogFileHandler
from backend.log_secrets import SecretRedactionFilter, install_secret_filter, remember_secret
from tests.backend.fixtures.logs import record


@pytest.mark.parametrize(
    "raw",
    [
        "Authorization: Bearer abcdefgh12345678",
        "ключ sk-abcdefghijklmnop0123",
        "api_hash='9cc8ccb459f977b52c89b3199fa8e591'",
        # Настоящая строка сеанса Pyrogram: base64 в безопасном для адреса
        # написании, с `-` и `_` внутри. Из одних больших букв её не собрать,
        # и образец, зелёный на «A» × 60, настоящую пропускал бы целиком.
        "сессия 4yNjo-QkZKTlJWWl5iZmpucnZ6foKGio6SlpqeoqaqrrK2ur7CxsrO0tba3uLm6u7y9vr_",
        # Pyrogram выкладывает в отладку каждое исходящее обращение целиком, и
        # на входе в Telegram это номер и одноразовый код открытым текстом.
        # Кольцо записей показывает их экраном «Логи»: человек, у которого
        # что-то пошло не так, снимает этот экран и отдаёт вместе с ними.
        # Две формы, потому что и пишет их Pyrogram двумя: разбор объекта
        # уходит в отладку словарём с отступами, а сам объект — своим `repr`.
        '"phone_number": "+79161234567"',
        '"phone_code": "12345"',
        '"phone_code_hash": "8e1a2b3c4d"',
        "auth.SendCode(phone_number='+79161234567', api_id=123)",
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


def test_what_stands_next_to_a_phone_stays_readable():
    """Затирка номера не съедает ни соседнее поле, ни следующую строку.

    Образец берёт цифры со скобками и дефисами, и пусти в него пробельное —
    он проглотил бы перевод строки, а с ним время и уровень следующей записи.
    Журнал бывает многострочным по многу причин, и вымаранная им запись
    перестала бы читаться вовсе.
    """
    entry = record("phone_number: 1234\nдальше [INFO] api_id=123 — это видно")

    SecretRedactionFilter().filter(entry)

    assert "дальше [INFO] api_id=123 — это видно" in entry.msg
    assert "1234" not in entry.msg


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


def test_an_unavailable_file_is_reported_to_the_stream(monkeypatch, capsys, tmp_path):
    """Когда и файл недоступен, беда уходит в поток ошибок."""
    monkeypatch.setattr("backend.log_secrets.get_log_path", lambda: tmp_path)

    LogBufferHandler().emit(_unbuildable())

    said = capsys.readouterr().err
    assert "не собирается" in said
    assert "Traceback" in said


def test_a_remembered_secret_never_reaches_the_record():
    remember_secret("abcd efgh ijkl mnop")
    entry = record("вход с паролем abcd efgh ijkl mnop не удался")

    SecretRedactionFilter().filter(entry)

    assert "abcd efgh ijkl mnop" not in entry.msg


def test_an_app_password_is_masked_even_when_unknown():
    entry = record("password=wxyz qrst uvwa bcde")

    SecretRedactionFilter().filter(entry)

    assert "wxyz qrst uvwa bcde" not in entry.msg


def test_an_ordinary_phrase_is_not_taken_for_a_password():
    entry = record("this will make sure")

    SecretRedactionFilter().filter(entry)

    assert entry.msg == "this will make sure"
