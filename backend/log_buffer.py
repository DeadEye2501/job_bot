"""In-memory ring buffer для UI-экрана «Логи».

Логи приложения уже идут в stderr через `logging.basicConfig`. Для UI
параллельно навешиваем `LogBufferHandler` на корневой logger, который
кладёт каждый record в bounded `deque`. UI забирает срез через bridge
slot с фильтрами по level/source/search.

Ring-buffer ограничен MAX_RECORDS — самые старые молча выпадают, чтобы
не утекать память при многочасовом аптайме.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from typing import Callable

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
            msg = record.msg
        # Traceback / exc-info → multi-line string; UI отображает в details.
        details: str | None = None
        if record.exc_info:
            try:
                details = self.format(record).rstrip()
            except Exception:
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
                # Не даём UI-callback'у уронить логирование.
                pass

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
    DEBUG-pill'а в UI. Stdout-handler (StreamHandler из basicConfig'а)
    остаётся на INFO, чтобы консоль не засрать.
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
