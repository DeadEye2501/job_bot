"""Журнал в памяти для экрана «Логи»: четыре кольца записей и снимок для окна.

Записи идут сюда с корневого logger'а; окно забирает снимок через мост и
отбирает у себя. Колец четыре — по одному на уровень, и предел у каждого свой
(`LEVEL_LIMITS`): самые старые записи **своего** уровня молча выпадают, чтобы
память не текла при многочасовой работе.

Порознь потому, что в общем кольце уровни вытесняли друг друга не по делу.
Отладка идёт потоком — сотни строк за один обход, — и смывала она ровно то,
ради чего журнал открывают: человек видел поломку, шёл разбираться, а строки о
ней к его приходу уже не было. Теперь отладка вытесняет только отладку.

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


LEVEL_LIMITS = {
    "ERROR": 500,
    "WARNING": 500,
    "INFO": 500,
    "DEBUG": 1500,
}
"""Сколько записей помнит журнал каждого уровня.

У отладки предел втрое больше не по щедрости: она и приходит на порядок чаще —
сотни строк за обход против единиц у предупреждения, — и мелкий предел стирал
бы её быстрее, чем человек успевает открыть экран.

`CRITICAL` живёт в журнале ошибок, а не своим: окно рисует их одной пилюлей и
одним цветом, и отдельный предел развёл бы число в пилюле со строками под ней.
Незнакомый уровень — тоже сюда, в отладочный: своего предела ему взять неоткуда,
а отладочный и есть ведро для шума.
"""

def _bucket_of(levelname: str) -> str:
    """В какое из четырёх колец ложится запись этого уровня.

    Правило одно на запись и на счёт в пилюле: разойдись они, пилюля обещала бы
    строки, которых в списке нет.
    """
    if levelname == "CRITICAL":
        return "ERROR"
    return levelname if levelname in LEVEL_LIMITS else "DEBUG"


class LogBufferHandler(logging.Handler):
    """Складирует LogRecord'ы по кольцу на уровень, опционально дёргает
    callback на каждый новый record (для push-сигнала в UI).
    """

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self._levels: dict[str, deque[dict]] = {
            name: deque(maxlen=limit) for name, limit in LEVEL_LIMITS.items()
        }
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
            self._levels[_bucket_of(record.levelname)].append(entry)
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
        """Все четыре кольца одной лентой, в порядке случившегося."""
        return self._taken()[0]

    def _taken(self) -> tuple[list[dict], dict[str, int]]:
        """Лента и счёт пилюль, снятые под одним замком.

        Порядок ленты восстанавливается по сквозному номеру записи: колец
        четыре, а лента у человека одна, и разложи мы её по уровням — из неё
        пропало бы главное, что за чем шло.

        Одним замком на оба — несущее. Возьми их порознь, между двумя
        обращениями успеет лечь новая запись или пройти очистка, и пилюля
        покажет «предупреждений 43» над сорока двумя строками. Сортировка при
        этом остаётся снаружи: держать под замком то, что кладут из любого
        потока, дольше, чем нужно, незачем.
        """
        with self._lock:
            together = [entry for ring in self._levels.values() for entry in ring]
            counts = {
                name: len(ring) for name, ring in self._levels.items() if ring
            }
        together.sort(key=lambda entry: entry["id"])
        return together, counts

    def page(self) -> dict:
        """Страница журнала для окна: записи, счёт по уровням и всего.

        Один снимок на всё: возьми записи и счётчики порознь — между двумя
        обращениями в кольцо успеет лечь новая запись, и число в пилюле не
        сойдётся со списком под ней.

        Счёт пилюли идёт по кольцу, а не по полю записи: в какое кольцо запись
        легла, решает `_bucket_of`, и своего правила у счёта больше нет — иначе
        пилюля обещала бы строки, которых под ней не покажется.

        Второе написание того же правила осталось в разметке (`pillOf` в
        `client/web/state/logs.js`), и зовут его оба тамошних дела — отбор,
        который окно делает у себя, и раскраска строки. Сведётся оно только
        вместе с переносом отбора на мост, а раскраска не сведётся вовсе: цвет
        — дело окна.

        Перечня источников в ответе нет: окно его не читает — берёт
        `records`, `level_counts` и `total`.

        Свежие сверху: окно рисует список сверху вниз.

        Потолка у страницы нет, и это несущее: отбор по уровню страница делает
        у себя, и обрежь мы список — пилюля обещала бы записи, которых человеку
        не достать ничем. Держат объём сами кольца: их пределы и есть потолок
        ответа.
        """
        records, level_counts = self._taken()
        return {
            "records": list(reversed(records)),
            "level_counts": level_counts,
            "total": len(records),
        }

    def clear(self) -> int:
        """Опустошить все четыре кольца и сказать, сколько записей убрано."""
        with self._lock:
            n = sum(len(ring) for ring in self._levels.values())
            for ring in self._levels.values():
                ring.clear()
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
