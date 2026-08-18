"""Ручной перезапуск разбора вакансии из окна."""

import logging

from typing import Literal

from backend.bot import slot

logger = logging.getLogger(__name__)


async def ui_rerun_vacancy_pipeline(
    bot, vacancy_id: int
) -> Literal["ok", "busy", "missing", "no_text", "llm", "cancelled", "error"]:
    """Re-parse / re-classify one vacancy — vacancies detail «more» menu.

    Идёт в общем месте прогона, как и обычный обход каналов: отсюда у
    пользователя штатный прогресс-бар и кнопка «остановить» в футере на
    время выполнения.

    Исход отдаётся словом, а не «да/нет»: занятое место, отмена и сорвавшаяся
    работа — три разных беды, и человеку про них говорят разное. Место прогона
    отвечает о своём, разбор — о своём, и его ответ сильнее: место видит
    удачей всё, что не бросило исключение.

    Нули в оповещении о прогрессе — «шкала неизвестна»: сколько шагов
    займёт разбор одной вакансии, заранее не знает никто.
    """
    logger.info("UI rerun pipeline for vacancy %d", vacancy_id)
    outcome, walk = await slot.run_in_slot(
        bot,
        lambda: bot.ingestion.rerun_pipeline_for_vacancy(vacancy_id),
        f"rerun pipeline for vacancy {vacancy_id}",
        progress=("rerun", f"Прогон вакансии #{vacancy_id}…", 0, 0),
    )
    return walk if outcome == "ok" else outcome
