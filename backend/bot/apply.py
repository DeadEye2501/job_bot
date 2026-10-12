"""Отклик по нажатию человека: тот же откликатель, в месте прогона с набором агента.

Нажатий два — выбранный способ одной вакансии и отклик на все новые разом.
Отличие от `bot/aggregators`: там — работа агента с источниками, здесь — отклик,
о котором попросил человек.
"""

from typing import Literal

from backend.agent.kit import AgentKit
from backend.applying import run
from backend.applying.result import Unfit
from backend.bot import work
from backend.domain.apply_order import Way
from backend.flows.handover import new_to_apply
from backend.models import Vacancy

ApplyOutcome = Literal[work.WorkOutcome, "failed", "unfit", "missing"]
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


async def apply_all_new(bot) -> work.WorkOutcome:
    """Откликнуться подряд на все новые разобранные вакансии. Режим не помеха: нажал человек.

    Список берётся уже в месте прогона: взятый до него разошёлся бы с тем, что
    успел сделать прогон, ждавший места.
    """

    async def apply(kit: AgentKit) -> str:
        await bot.ingestion.reload_resources()
        await run.apply_vacancies(kit, await new_to_apply(bot.session_factory))
        return "ok"

    return await work.in_slot(bot, apply, "apply all new")
