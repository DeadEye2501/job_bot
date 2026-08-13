"""Системный журнал в окне: страница записей, подписка, очистка."""

from __future__ import annotations

import json
import logging
import time

from PySide6.QtCore import Signal, Slot

from backend.log_buffer import get_handler
from backend.payloads import int_or_none
from client.bridge.answer import _err, _ok
from client.bridge.payload import _log_invalid_payload


logger = logging.getLogger(__name__)

_LOGS_PAGE = 1000
"""Сколько записей уезжает в окно, если оно не просило иного."""

_LOGS_REQUEST_INTERVAL_S = 1.0
"""Чаще раза в секунду журнал не спрашивают.

Окно опрашивает его по своим часам, а новые записи и так приходят подпиской:
второе обращение за ту же секунду отдало бы тот же снимок.
"""


class JournalSlots:
    """Буфер журнала, каким его видит окно.

    Подмешивающий обязан держать `_dispatch` и признак `_logs_subscribed`:
    подписку ставит окно, а строки в неё толкает обработчик, заведённый
    подмешивающим при сборке, — поэтому `system_log_record_pushed` объявлен
    здесь, а испускается не отсюда.
    """

    system_logs_loaded = Signal(str)
    system_log_record_pushed = Signal(str)
    system_logs_cleared = Signal(str)

    @Slot(str)
    def request_system_logs(self, payload_json: str) -> None:
        """Страница журнала для экрана «Логи».

        Нагрузка — `{limit?}`. Отбора здесь нет нарочно: окно берёт весь
        буфер и отбирает у себя, потому что счётчики в пилюлях считают полный
        буфер независимо от выбранного уровня. Три ветки отбора, стоявшие
        тут прежде, окно не просило ни разу — и одна из них разошлась с
        общим правилом поиска.

        Заслон от частых обращений: окно опрашивает журнал по своим часам, и
        второе обращение за секунду ничего не добавит — записи оно и так
        получит подпиской.

        Потолок не зажимается: больше кольца (`log_buffer.MAX_RECORDS`) в
        ответе и не бывает, а зажим на границе выглядел бы правилом, которого
        нет.
        """
        now = time.monotonic()
        if now - self._logs_request_last_ts < _LOGS_REQUEST_INTERVAL_S:
            logger.debug("request_system_logs: too often, skipped")
            return
        self._logs_request_last_ts = now
        try:
            payload = json.loads(payload_json) if payload_json else {}
            limit = int_or_none(payload.get("limit")) or _LOGS_PAGE
        except (AttributeError, ValueError, TypeError) as e:
            _log_invalid_payload("request_system_logs", e)
            self.system_logs_loaded.emit(_err(f"Неверные поля: {e}"))
            return

        async def run() -> str:
            return _ok(get_handler().page(limit))

        self._dispatch(self.system_logs_loaded, run())

    @Slot(bool)
    def set_logs_subscribed(self, subscribed: bool) -> None:
        """JS toggle'ит при заходе/уходе с logs-таба и при включении/
        выключении auto-refresh. Когда False, push-сигнал гасится в
        источнике: обработчик буфера журнала, который заводит подмешивающий
        при сборке, читает этот признак перед каждой отправкой.
        """
        self._logs_subscribed = bool(subscribed)

    @Slot()
    def request_system_logs_clear(self) -> None:
        """Очищает in-memory ring-buffer. Не трогает файлы/stdout — это
        чисто UI-action для сброса видимого списка.
        """
        async def run() -> str:
            cleared = get_handler().clear()
            return _ok({"cleared": cleared})

        self._dispatch(self.system_logs_cleared, run())
