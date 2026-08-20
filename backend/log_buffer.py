"""Журнал в памяти для экрана «Логи»: кольцо записей и снимок для окна.

Записи идут сюда с корневого logger'а и ложатся в bounded `deque`; окно
забирает срез через мост с отборами по уровню, источнику и поиску. Кольцо
ограничено `MAX_RECORDS` — самые старые молча выпадают, чтобы память не текла
при многочасовой работе.

Соседи по слою — `log_secrets` (вымарывание и жалоба на свою беду) и
`log_file` (файл журнала). Связку из них собирает точка входа, и порядок трёх
шагов там не случаен: `main._log_handlers` заводит файл и поток, `install()`
вешает это кольцо, и только потом `log_secrets.install_secret_filter()` —
вымарывание садится на уже навешенные обработчики, а не на logger, и
поставленное раньше не накрыло бы ни файла, ни кольца.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from typing import Callable

from backend.log_secrets import report_own_failure


MAX_RECORDS = 5000

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

    def page(self) -> dict:
        """Страница журнала для окна: записи, счёт по уровням и всего.

        Один снимок на всё: возьми записи и счётчики порознь — между двумя
        обращениями в кольцо успеет лечь новая запись, и число в пилюле не
        сойдётся со списком под ней.

        `CRITICAL` считается `ERROR`'ом: окно рисует их одним цветом, и
        отдельная пилюля с единицей заставляла бы искать разницу, которой
        человеку не показывают. В питоне это правило одно и живёт здесь;
        второе написание осталось в разметке (`pillOf` в
        `client/web/state/logs.js`), и зовут его оба тамошних дела — отбор,
        который окно делает у себя, и раскраска строки. Сведётся оно только
        вместе с переносом отбора на мост, а раскраска не сведётся вовсе: цвет
        — дело окна.

        Перечня источников в ответе нет: окно его не читает — берёт
        `records`, `level_counts` и `total`.

        Свежие сверху: окно рисует список сверху вниз.

        Потолка у страницы нет, и это несущее: счётчики считают всё кольцо, а
        отбор по уровню страница делает у себя. Обрежь мы список — пилюля
        обещала бы записи, которых человеку не достать ничем: он нажимает
        «ошибок 1200» и находит тысячу.

        Цена у этого есть, и она названа: полное кольцо — порядка мегабайта
        JSON на зов, много больше с трассировками, а под нагрузкой окно
        спрашивает его примерно раз в секунду. Отрисовку спасает отбор по
        уровню, который окно делает у себя, но нажатие DEBUG на полном кольце
        рисует все `MAX_RECORDS` строк разом. Резать поэтому придётся либо само
        кольцо, либо список на экране — но не страницу здесь: вернётся ровно то,
        от чего потолок и сняли.
        """
        records = self.snapshot()
        level_counts: dict[str, int] = {}
        for entry in records:
            level = "ERROR" if entry["level"] == "CRITICAL" else entry["level"]
            level_counts[level] = level_counts.get(level, 0) + 1
        return {
            "records": list(reversed(records)),
            "level_counts": level_counts,
            "total": len(records),
        }

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
