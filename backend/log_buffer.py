"""In-memory ring buffer для UI-экрана «Логи», вымарывание секретов и отчёт
о собственной беде — три дела одного слоя, того, что стоит между записью и
её получателями.

Логи приложения уже идут в файл и, если есть куда, в поток вывода — собирает
эту связку `main._log_handlers`, а сам файловый обработчик объявлен здесь: о
своей беде он отчитывается тем же способом, что и буфер. Для UI параллельно
навешиваем `LogBufferHandler` на корневой logger, который кладёт каждый record
в bounded `deque`. UI забирает срез через bridge slot с фильтрами по
level/source/search.

Ring-buffer ограничен MAX_RECORDS — самые старые молча выпадают, чтобы
не утекать память при многочасовом аптайме.

`report_own_failure` — единственный способ пожаловаться, доступный тому, кто
сам обслуживает жалобы: обычная запись ушла бы по кругу.
"""

from __future__ import annotations

import logging
import re
import sys
import threading
import traceback
from collections import deque
from contextlib import suppress
from datetime import datetime
from logging.handlers import RotatingFileHandler
from typing import Callable

from config import get_log_path

MAX_RECORDS = 5000


# === Defence-in-depth: scrub известные паттерны секретов ===================
# В коде ни один logger.* специально секреты не пишет (audited). Но третьи
# либы (httpx debug-mode, pyrogram, sqlalchemy echo) могут засветить
# Authorization-header или строку коннекта; SecretRedactionFilter ловит
# это до того как record уезжает в stdout и в UI-buffer.
_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]+", re.IGNORECASE),
    re.compile(r"sk-[A-Za-z0-9_\-]{16,}"),
    re.compile(
        r"(api_hash[\"']?\s*[:=]\s*[\"']?)[a-f0-9]{32}",
        re.IGNORECASE,
    ),
    # Telegram session-string (base64-ish blob с : разделителями) —
    # эвристика: 50+ символов A-Za-z0-9+/=:_-. Слишком короткое не
    # маскируем — false-positive risk.
    re.compile(r"\b[A-Za-z0-9+/=]{60,}\b"),
)
_REDACTED = "***"


def report_own_failure(what: str, record: logging.LogRecord) -> None:
    """Сказать о беде внутри самого журналирования, минуя логирование.

    Обычная запись ушла бы по кругу: беда случилась в обработчике логов.
    Штатный для такого `handleError` печатает в поток ошибок, а в оконной
    сборке (`console=False`) потока нет вовсе — остаётся тот же файл, куда
    идёт журнал. Довод записан здесь один раз; остальные места на него
    ссылаются.

    Файл открывается на одну запись и сразу закрывается: им владеет
    `RotatingFileHandler`, и держать второй описатель открытым значит
    однажды сорвать ему переход на новый файл.
    """
    try:
        stamp = f"{datetime.now():%Y-%m-%d %H:%M:%S,%f}"[:-3]
        # Шаблон читается и вымарывается здесь, а не у зовущего: `__repr__`
        # у него бывает сломан, и тогда жалоба превратилась бы в падение
        # того, кто просто позвал `logger.*`. Вымарывание обязательно —
        # собрать сообщение не удалось, значит обычный путь секрет не убрал.
        line = (
            f"{stamp} [ERROR] backend.log_buffer: {what}: "
            f"{_redact(repr(record.msg))}\n"
        )
        with open(get_log_path(), "a", encoding="utf-8", errors="replace") as out:
            out.write(line + traceback.format_exc())
    except Exception:
        # Файла нет или он недоступен — остаётся поток ошибок, которого в
        # оконной сборке нет. Дальше этого рубежа сказать нечем.
        if sys.stderr is not None:
            with suppress(OSError, ValueError):
                sys.stderr.write(f"backend.log_buffer: {what}\n")
                traceback.print_exc()


def _redact(text: str) -> str:
    out = text
    for pat in _SECRET_PATTERNS:
        out = pat.sub(_REDACTED, out)
    return out


class SecretRedactionFilter(logging.Filter):
    """Применяет _redact к message и exc_text. Ставится на обработчики
    корневого logger'а через ``install_secret_filter()``."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            # Сообщение не собралось — значит и вымарать секрет в нём нечем.
            # Запись пропускается дальше, но молчать о ней нельзя: именно в
            # такой секрет и уедет незамаскированным.
            #
            # Отметка на записи — от размножения: фильтр висит на каждом
            # обработчике своим экземпляром, и без неё об одной записи
            # сообщили бы все трое.
            if not getattr(record, "own_failure_reported", False):
                record.own_failure_reported = True
                report_own_failure("запись не собирается", record)
            return True
        scrubbed = _redact(msg)
        if scrubbed != msg:
            record.msg = scrubbed
            record.args = ()
        # Трассировку приходится собирать здесь самим. Обычно её собирает
        # форматтер, но он работает уже внутри обработчика, то есть после
        # фильтров: первый обработчик по списку — в бою файловый — записал бы
        # текст исключения до всякого вымарывания. Собранное кладётся в саму
        # запись, форматтер потом берёт готовое.
        if record.exc_info and not record.exc_text:
            try:
                record.exc_text = "".join(
                    traceback.format_exception(*record.exc_info)
                ).rstrip("\n")
            except Exception:
                # Фильтр работает до защитного перехвата вокруг записи, и своё
                # падение здесь ушло бы наружу — тому, кто просто позвал
                # `logger.exception` внутри своего `except`. Трассировку в
                # этом случае соберёт форматтер: он-то как раз под защитой.
                if not getattr(record, "own_failure_reported", False):
                    record.own_failure_reported = True
                    report_own_failure("трассировка записи не собирается", record)
        if record.exc_text:
            record.exc_text = _redact(record.exc_text)
        return True


def install_secret_filter() -> None:
    """Идемпотентно ставит SecretRedactionFilter на каждый обработчик корня.

    На сам logger вешать нельзя, хотя и хочется: фильтр logger'а разбирает
    только записи, сделанные им самим, а до обработчиков предка запись
    доходит мимо его фильтров. Записи третьих библиотек — httpx, pyrogram,
    sqlalchemy — идут именно так, и ради них фильтр и заведён.
    """
    for handler in logging.getLogger().handlers:
        if not any(isinstance(f, SecretRedactionFilter) for f in handler.filters):
            handler.addFilter(SecretRedactionFilter())


class LogFileHandler(RotatingFileHandler):
    """Обработчик файла журнала, говорящий о своей беде — и только раз.

    Беда у него одна и повторяющаяся: переход на новый файл. Пока файл открыт
    кем-то ещё, Windows не даёт его переименовать, `doRollover` отвечает
    отказом — и в тот же отказ упирается каждая следующая запись, потому что
    разросшийся файл так и остался на месте.

    Отсюда и засов. Жалоба на каждую запись была бы не лучше молчания:
    ограничивать размер файла уже нечем, и повторяющаяся трассировка растила
    бы ровно тот файл, которому не удаётся повернуться.
    """

    _complained = False

    def handleError(self, record: logging.LogRecord) -> None:
        if self._complained:
            return
        self._complained = True
        report_own_failure("файл журнала не принял запись", record)


class LogBufferHandler(logging.Handler):
    """Складирует LogRecord'ы в shared deque, опционально дёргает callback
    на каждый новый record (для push-сигнала в UI).
    """

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self._records: deque[dict] = deque(maxlen=MAX_RECORDS)
        self._lock = threading.Lock()
        self._counter = 0
        self.on_record: Callable[[dict], None] | None = None

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = record.getMessage()
        except Exception:
            report_own_failure("сообщение записи не собирается", record)
            msg = record.msg
        # Traceback / exc-info → multi-line string; UI отображает в details.
        details: str | None = None
        if record.exc_info:
            try:
                details = self.format(record).rstrip()
            except Exception:
                report_own_failure("трассировка записи не собирается", record)
                details = None
        with self._lock:
            self._counter += 1
            entry = {
                "id": self._counter,
                "ts": record.created,            # epoch seconds (float)
                "level": record.levelname,       # DEBUG/INFO/WARNING/ERROR/...
                "source": record.name,           # logger name
                "msg": str(msg),
                "details": details,
            }
            self._records.append(entry)
        if self.on_record is not None:
            try:
                self.on_record(entry)
            except Exception:
                # Уронить логирование подписчик не должен, но и молчать о нём
                # нельзя. `handleError` для того и заведён — он же и переопределён
                # ниже, потому что штатный печатает в поток ошибок.
                self.handleError(record)

    def handleError(self, record: logging.LogRecord) -> None:
        """Сказать о беде обработчика в файл журнала, а не в поток ошибок.

        Штатный `handleError` печатает в `sys.stderr`, а у оконной сборки его
        нет — и всё, что он сообщал, пропадало."""
        report_own_failure("обработчик буфера подавился записью", record)

    def snapshot(self) -> list[dict]:
        with self._lock:
            return list(self._records)

    def clear(self) -> int:
        with self._lock:
            n = len(self._records)
            self._records.clear()
        return n


# Module-level singleton: ставится один раз при загрузке модуля,
# вешается на root в install().
_handler = LogBufferHandler()


def install() -> LogBufferHandler:
    """Атачит buffer-handler на корневой logger. Идемпотентно.

    Опускаем уровень корневого logger'а до DEBUG (если basicConfig поставил
    INFO), чтобы DEBUG-записи доходили до buffer'а — они нужны для
    DEBUG-pill'а в UI. Остальные обработчики остаются на INFO, и это про оба:
    консоль не засорить, а файл журнала не раздуть. DEBUG в цикле опроса и в
    разборе оповещений идёт потоком, и пять мегабайт файла он съел бы за час,
    вытеснив то, ради чего файл заведён, — историю до падения.
    """
    root = logging.getLogger()
    if _handler not in root.handlers:
        root.addHandler(_handler)
    if root.level == logging.NOTSET or root.level > logging.DEBUG:
        # Stash прежний level, ставим на handler'ы which were configured by basicConfig.
        existing_level = root.level if root.level != logging.NOTSET else logging.INFO
        for h in root.handlers:
            if h is _handler:
                continue
            if h.level == logging.NOTSET:
                h.setLevel(existing_level)
        root.setLevel(logging.DEBUG)
    return _handler


def get_handler() -> LogBufferHandler:
    return _handler
