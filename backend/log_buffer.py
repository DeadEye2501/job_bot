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
import re
import threading
from collections import deque
from typing import Callable

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


def _redact(text: str) -> str:
    out = text
    for pat in _SECRET_PATTERNS:
        out = pat.sub(_REDACTED, out)
    return out


class SecretRedactionFilter(logging.Filter):
    """Применяет _redact к message и exc_text. Ставится на root logger
    через ``install_secret_filter()``; работает на ВСЕ handlers одинаково."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return True
        scrubbed = _redact(msg)
        if scrubbed != msg:
            record.msg = scrubbed
            record.args = ()
        if record.exc_text:
            record.exc_text = _redact(record.exc_text)
        return True


def install_secret_filter() -> None:
    """Идемпотентно ставит SecretRedactionFilter на root logger."""
    root = logging.getLogger()
    for f in root.filters:
        if isinstance(f, SecretRedactionFilter):
            return
    root.addFilter(SecretRedactionFilter())


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
