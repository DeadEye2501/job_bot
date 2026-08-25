"""Заведение вакансии по вставленному тексту — из окна."""

import logging
from datetime import datetime
from typing import Literal

from backend.bot import slot
from backend.flows import pasted as flow_pasted

logger = logging.getLogger(__name__)

PastedOutcome = Literal[slot.CycleOutcome, flow_pasted.PastedIntakeOutcome]
"""Чем кончилось заведение по вставленному тексту, как это видит окно.

Складывается по тому же уговору, что и исход повторного прогона: место
прогона отвечает о своём, приём — о своём.
"""


async def ui_ingest_pasted_text(
    bot, text: str, posted_at: datetime | None
) -> PastedOutcome:
    """Принять вставленное объявление в общем месте прогона.

    Там же, где обход каналов и повторный разбор: у приёма те же обращения к
    модели и тот же кэш отпечатков, а два прогона разом подрались бы за них.
    Отсюда же человек получает штатную полосу и кнопку «остановить».

    Нули в оповещении о прогрессе — «шкала неизвестна»: сколько шагов займёт
    разбор одного объявления, заранее не знает никто.
    """
    logger.info("UI ingest of pasted text, %d chars", len(text))
    outcome, walk = await slot.run_in_slot(
        bot,
        lambda: bot.ingestion.ingest_pasted_text(text, posted_at),
        "ingest pasted text",
        progress=("pasted", "Разбор вставленного объявления…", 0, 0),
    )
    return walk if outcome == "ok" else outcome
