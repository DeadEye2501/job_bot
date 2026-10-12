"""Ручной отклик выбранным способом: тот же откликатель, в месте прогона с набором агента.

Отличие от `bot/aggregators`: там — работа агента с источниками, здесь — отклик
по нажатию человека на любой способ, от Telegram до формы.
"""

from typing import Literal

from backend.agent.kit import AgentKit
from backend.applying import run
from backend.applying.result import Unfit
from backend.bot import slot, work
from backend.domain.apply_order import Way
from backend.models import Vacancy

ApplyOutcome = Literal[slot.CycleOutcome, work.AgentStop, "failed", "unfit", "missing"]
"""Чем кончился ручной отклик: исходы места прогона и работы с агентом, свой
провал способа, вакансия, оказавшаяся неподходящей, и пропавшая вакансия."""


async def apply_chosen_way(bot, vacancy_id: int, way: Way) -> ApplyOutcome:
    """Откликнуться выбранным способом. Режим ему не помеха: нажал человек."""
    async with bot.session_factory() as session:
        if await session.get(Vacancy, vacancy_id) is None:
            return "missing"

    async def apply(kit: AgentKit) -> str:
        # Анкета в памяти конвейера свежа после оборота, а нажать можно и до
        # первого: письмо без неё не сочинить.
        await bot.ingestion.reload_resources()
        outcome = await run.apply_chosen(kit, vacancy_id, way)
        if outcome == "applied":
            return "ok"
        return "unfit" if isinstance(outcome, Unfit) else "failed"

    return await work.in_slot(bot, apply, f"apply {way.method} {vacancy_id}")
