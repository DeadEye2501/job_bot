"""Заведение вакансии из окна, которое ведёт бот: текст, ссылка и поля к отклику — в месте прогона."""

import logging
from dataclasses import replace
from typing import Literal

from backend.bot import work
from backend.bot.aggregators import aggregators_available
from backend.domain.hosts import link_kind
from backend.flows import hand_made as flow_hand_made
from backend.flows.hand_made import HandRequest

logger = logging.getLogger(__name__)

HandMadeOutcome = Literal[work.WorkOutcome, "told", "locked"]
"""Чем кончилась работа заведения, как это видит окно.

«Сказано» значит, что второй вести не нужно. «Заперто» — страницу по ссылке
читает агент, а его сейчас нет. Остальное — отказы места прогона, до итога
заведения не дошедшего. Сам итог заведения (`flows.hand_outcome.HandOutcome`)
сюда не входит: он уходит окну вестью по ходу работы.
"""


async def ui_ingest_by_hand(bot, request: HandRequest) -> HandMadeOutcome:
    """Повести заявку окна в общем месте прогона.

    Там же, где обход каналов и повторный разбор: у приёма те же обращения к
    модели и тот же кэш отпечатков, а два прогона разом подрались бы за них.
    Отсюда же человек получает штатную полосу и кнопку «остановить».

    Сказанный итог сильнее того, чем кончилась работа: отклик после него мог
    сорваться — сроком, «Стопом», бедой, — но вакансия уже стоит в New, и
    вторая весть «не удалось завести» была бы неправдой. О срыве отклика окно
    узнаёт своим путём (`work.agent_work`).
    """
    if request.tab == "link":
        # Род ссылки решается здесь, один раз: ниже заявка идёт уже им.
        request = replace(request, tab=link_kind(request.value))
        if request.tab == "page" and aggregators_available(bot) is not None:
            return "locked"
    logger.info("UI hand-made vacancy from tab %s", request.tab)
    bot.ingestion.hand_made_told = False

    # Сказан ли итог, решается одной строкой ниже: работа, дошедшая до конца,
    # отвечает бедой, и её перекрывает сказанный итог — без него кончившаяся
    # молча работа осталась бы окну неслышной.
    async def job(kit) -> str:
        await flow_hand_made.ingest_by_hand(kit, request)
        return "error"

    outcome = await work.in_slot(bot, job, "ingest by hand")
    return work.TOLD if bot.ingestion.hand_made_told else outcome
