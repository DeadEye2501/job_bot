"""Единый конверт ответа окну — от исхода работы до сигнала."""

from __future__ import annotations

import asyncio
import json
import logging
from concurrent.futures import CancelledError, Future
from datetime import datetime, timezone
from typing import Any, Coroutine

from PySide6.QtCore import SignalInstance

from client.bridge.runner import AsyncRunner


logger = logging.getLogger(__name__)


def _ok(data: dict | None = None) -> str:
    return json.dumps({"ok": True, **(data or {})})


def _err(message: str, **extra: Any) -> str:
    return json.dumps({"ok": False, "error": message, **extra})


def _iso(dt: datetime | None) -> str | None:
    """ISO-8601 с обязательным TZ-суффиксом, под JS `Date.parse`.

    SQLite + ``DateTime(timezone=True)`` хранит как text. Строки, записанные
    через ``server_default=func.now()`` (vacancy_status_history.changed_at,
    vacancy_event.created_at и т.п.) приходят обратно naive — без offset'а.
    Голый ``.isoformat()`` шлёт `"2026-05-07T12:34:56"` без `Z`/`+00:00`,
    а `Date.parse` без TZ интерпретирует строку как ЛОКАЛЬНОЕ время —
    свежий эвент превращается в «N часов назад» на величину TZ-оффсета.
    Naive значения трактуем как UTC (потому что вся запись идёт в UTC),
    aware — отдаём как есть.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _dispatch_json(
    runner: AsyncRunner, signal: SignalInstance, coro: Coroutine[Any, Any, Any]
) -> None:
    """Отправить корутину на runner и отдать её ответ окну сигналом.

    Объявлено один раз на оба класса: общие чтения нагрузки зовут отправку,
    не зная, у какого из них они в руках, — а разойдись эти отправки, у
    мастера и настроек разошлось бы и поведение при закрытии окна.

    Отмену при остановке не показываем: обработчик в окне к этому мигу уже
    отвалился, и «CancelledError» уходило бы в умирающую страницу. Обе
    породы отмены ловятся вместе — runner отдаёт свою, корутина свою.
    """
    future = runner.submit(coro)

    def on_done(f: Future) -> None:
        try:
            payload = f.result()
        except (CancelledError, asyncio.CancelledError):
            return
        except Exception as e:
            logger.exception(
                "bridge: unexpected error in coroutine %s",
                getattr(coro, "__qualname__", "?"),
            )
            payload = _err(f"{type(e).__name__}: {e}")
        signal.emit(payload)

    future.add_done_callback(on_done)
