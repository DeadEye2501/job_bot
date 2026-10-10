"""Срок, до которого Telegram просил не писать: запись и снятие."""

import logging
import time

logger = logging.getLogger(__name__)


async def note_flood_wait(rs, error) -> float:
    """Запомнить, до какого времени Telegram просил не писать; отдать этот срок.

    Запись переживает перезапуск нарочно: откликатель читает её в начале
    прогона и не предлагает Telegram, пока срок не выйдет.
    """
    secs = int(getattr(error, "value", 0) or 0)
    until = time.time() + secs
    logger.warning("Telegram: FloodWait %d сек, запоминаю срок", secs)
    try:
        await rs.set_app("flood_wait_until_ts", str(until))
    except Exception:
        logger.exception("Telegram: срок FloodWait не записан")
    return until


async def clear_flood_wait(rs) -> None:
    """Снять запрет: Telegram отпустил, и ждать больше нечего."""
    if rs.flood_wait_until_ts <= 0:
        return
    try:
        await rs.set_app("flood_wait_until_ts", "0")
    except Exception:
        logger.exception("Telegram: срок FloodWait не снят")
