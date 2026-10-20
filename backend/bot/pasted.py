"""Заведение вакансии из окна, которое ведёт бот: вставленный текст и поля к отклику."""

import logging
from typing import Literal

from backend.bot import work
from backend.flows import hand_made
from backend.flows.hand_made import HandRequest

logger = logging.getLogger(__name__)

TOLD = work.TOLD

PastedOutcome = Literal[work.WorkOutcome, "told"]
"""Чем кончилась работа заведения, как это видит окно.

«Сказано» значит, что второй вести не нужно. Остальное — отказы места
прогона, до итога заведения не дошедшего.
"""


async def ui_ingest_pasted_text(bot, request: HandRequest) -> PastedOutcome:
    """Повести заявку окна в общем месте прогона.

    Там же, где обход каналов и повторный разбор: у приёма те же обращения к
    модели и тот же кэш отпечатков, а два прогона разом подрались бы за них.
    Отсюда же человек получает штатную полосу и кнопку «остановить».

    Сказанный итог сильнее того, чем кончилась работа: отклик после него мог
    сорваться — сроком, «Стопом», бедой, — но вакансия уже стоит в New, и
    вторая весть «не удалось завести» была бы неправдой. О срыве отклика окно
    узнаёт своим путём (`work.agent_work`).
    """
    logger.info("UI hand-made vacancy from tab %s", request.tab)
    bot.ingestion.hand_made_told = False

    async def job(kit) -> str:
        await hand_made.ingest_by_hand(kit, request)
        return TOLD

    outcome = await work.in_slot(bot, job, "ingest by hand")
    return TOLD if bot.ingestion.hand_made_told else outcome
