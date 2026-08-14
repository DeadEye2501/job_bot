"""Жалоба в журнал на негодную нагрузку, пришедшую из окна."""

from __future__ import annotations

import logging


logger = logging.getLogger(__name__)


def _log_invalid_payload(slot: str, exc: Exception) -> None:
    """Порода ошибки без её текста: `int()` вставляет туда само значение, а
    нагрузка несёт api_hash, ключ модели и пароль — образцы вымарывания хэш
    без имени поля рядом не ловят. У `KeyError` текст — имя поля, и оно живёт.
    """
    missing = exc.args[0] if isinstance(exc, KeyError) and exc.args else None
    said = f"нет поля {missing!r}" if missing is not None else type(exc).__name__
    logger.warning("%s: invalid payload: %s", slot, said)
