"""Ручной перезапуск разбора вакансии из окна."""

import logging

from backend.bot import slot

logger = logging.getLogger(__name__)


async def ui_rerun_vacancy_pipeline(bot, vacancy_id: int) -> bool:
    """Re-parse / re-classify one vacancy — vacancies detail «more» menu.

    Идёт в общем месте прогона, как и обычный обход каналов: отсюда у
    пользователя штатный прогресс-бар и кнопка «остановить» в футере на
    время выполнения. Место занято — возвращаем False, и окно показывает
    подсказку «не удалось перезапустить».

    Нули в оповещении о прогрессе — «шкала неизвестна»: сколько шагов
    займёт разбор одной вакансии, заранее не знает никто.
    """
    logger.info("UI rerun pipeline for vacancy %d", vacancy_id)
    outcome, ok = await slot.run_in_slot(
        bot,
        lambda: bot._ingestion.rerun_pipeline_for_vacancy(vacancy_id),
        f"rerun pipeline for vacancy {vacancy_id}",
        progress=("rerun", f"Прогон вакансии #{vacancy_id}…", 0, 0),
    )
    return bool(ok) if outcome == "ok" else False
