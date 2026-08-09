"""Ручной перезапуск разбора вакансии из окна."""

import logging
import asyncio

logger = logging.getLogger(__name__)


async def ui_rerun_vacancy_pipeline(bot, vacancy_id: int) -> bool:
    """Re-parse / re-classify one vacancy — vacancies detail «more» menu.

    Wraps the rerun in the same ``_current_poll_task`` slot + cycle
    hooks как обычный poll-цикл — это даёт юзеру штатный прогресс-бар
    и кнопку «остановить» в футере на время выполнения. Если уже
    идёт другой цикл, сигнализируем «busy» через возврат False —
    UI покажет toast про «не удалось перезапустить».
    """
    logger.info("UI rerun pipeline for vacancy %d", vacancy_id)
    if bot._current_poll_task is not None:
        logger.info("ui_rerun: another cycle is already running, skipping")
        return False
    if bot.on_cycle_start is not None:
        try: bot.on_cycle_start()
        except Exception: logger.exception("on_cycle_start hook failed")
    if bot.on_progress is not None:
        try: bot.on_progress("rerun", f"Прогон вакансии #{vacancy_id}…", 0, 0)
        except Exception: logger.exception("on_progress hook failed")
    ok = False
    try:
        bot._current_poll_task = asyncio.create_task(
            bot._ingestion.rerun_pipeline_for_vacancy(vacancy_id)
        )
        try:
            ok = await bot._current_poll_task
        except asyncio.CancelledError:
            logger.info("rerun pipeline for vacancy %d cancelled by user", vacancy_id)
    except Exception:
        logger.exception("rerun pipeline for vacancy %d failed", vacancy_id)
    finally:
        bot._current_poll_task = None
        if bot.on_cycle_end is not None:
            try: bot.on_cycle_end()
            except Exception: logger.exception("on_cycle_end hook failed")
    return ok
