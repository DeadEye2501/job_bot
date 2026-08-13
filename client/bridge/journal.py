"""Системный журнал в окне: страница записей, подписка, очистка."""

from __future__ import annotations

import json
import logging

from PySide6.QtCore import Signal, Slot

from backend.log_buffer import get_handler
from client.bridge.answer import _err, _ok
from client.bridge.payload import _log_invalid_payload


logger = logging.getLogger(__name__)


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
        """Snapshot текущего log-buffer'а с фильтрами по level/source/search.

        Payload: ``{level?, source?, search?, limit?}``. level — точное
        совпадение на levelname, source — startswith (logger 'backend.flows'
        матчит фильтр 'backend'), search — substring case-insensitive по
        msg+details.

        Дешёвая 1-сек защита от auto-fire'а из JS (например, log-poll'а в
        пол-секунды): второй вызов в окне 1 секунды считается избыточным,
        UI всё равно перерендерится через подписку на push-сигнал.
        """
        import time as _time
        last_ts = getattr(self, "_logs_request_last_ts", 0.0)
        now = _time.time()
        if now - last_ts < 1.0:
            logger.debug("request_system_logs: debounced (interval %.2fs)", now - last_ts)
            return
        self._logs_request_last_ts = now
        try:
            payload = json.loads(payload_json) if payload_json else {}
            level = payload.get("level")
            source = payload.get("source")
            search = payload.get("search")
            limit = int(payload.get("limit") or 1000)
            if limit > 5000:
                limit = 5000
        except (ValueError, TypeError) as e:
            _log_invalid_payload("request_system_logs", e)
            self.system_logs_loaded.emit(_err(f"Неверные поля: {e}"))
            return

        async def run() -> str:
            # Один snapshot для всего: иначе race между среза'ми может
            # дать инконсистентные records vs counts.
            all_records = get_handler().snapshot()
            sources = sorted({r["source"] for r in all_records})
            level_counts: dict[str, int] = {}
            for r in all_records:
                lvl = r["level"]
                # CRITICAL рендерится как ERROR в UI — счётчик объединяем,
                # чтобы ERROR-pill не недоучитывал.
                if lvl == "CRITICAL":
                    lvl = "ERROR"
                level_counts[lvl] = level_counts.get(lvl, 0) + 1

            records = all_records
            if level:
                if level == "ERROR":
                    records = [r for r in records if r["level"] in ("ERROR", "CRITICAL")]
                else:
                    records = [r for r in records if r["level"] == level]
            if source:
                records = [r for r in records if r["source"].startswith(source)]
            if search:
                q = search.casefold()
                records = [
                    r for r in records
                    if q in r["msg"].casefold()
                    or (r.get("details") and q in r["details"].casefold())
                ]
            # Newest-first; UI рендерит сверху-вниз.
            records = list(reversed(records))[:limit]
            return _ok({
                "records": records,
                "sources": sources,
                "level_counts": level_counts,
                "total": len(all_records),
            })

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
