"""Ручной перезапуск разбора вакансии из окна."""

import logging

from typing import Literal

from backend.bot import slot
from backend.flows import rerun as flow_rerun

logger = logging.getLogger(__name__)

RerunOutcome = Literal[slot.CycleOutcome, flow_rerun.RerunPipelineOutcome]
"""Чем кончился повторный прогон вакансии, как это видит окно.

Складывается по тому же уговору, что `channels.ChannelPollOutcome`.
"""


async def ui_rerun_vacancy_pipeline(bot, vacancy_id: int) -> RerunOutcome:
    """Re-parse / re-classify one vacancy — vacancies detail «more» menu.

    Идёт в общем месте прогона, как и обычный обход каналов: отсюда у
    пользователя штатный прогресс-бар и кнопка «остановить» в футере на
    время выполнения.

    Исход отдаётся словом, а не «да/нет»: занятое место, отмена и сорвавшаяся
    работа — три разных беды, и человеку про них говорят разное.

    Нули в оповещении о прогрессе — «шкала неизвестна»: сколько шагов
    займёт разбор одной вакансии, заранее не знает никто.
    """
    logger.info("UI rerun pipeline for vacancy %d", vacancy_id)
    return await slot.answer_in_slot(
        bot,
        lambda: bot.ingestion.rerun_pipeline_for_vacancy(vacancy_id),
        f"rerun pipeline for vacancy {vacancy_id}",
        progress=("rerun", f"Прогон вакансии #{vacancy_id}…", 0, 0),
    )
