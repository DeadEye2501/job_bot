"""Цикл откликателя: по каждой вакансии первый доступный способ, пока один не удастся."""

import logging
from collections.abc import Awaitable, Callable

from sqlalchemy import select

from backend.agent.kit import AgentKit
from backend.agent.stops import RUN_STOPPERS
from backend.applying.browser import via_browser
from backend.applying.email import via_email
from backend.applying.result import Missed, Outcome
from backend.applying.telegram import via_telegram
from backend.applying.world import awaits_application, learn, read_world, ways_in
from backend.domain.apply_order import VIA_AGGREGATOR, VIA_EMAIL, VIA_FORM, VIA_TELEGRAM, Way, World
from backend.models import Vacancy

logger = logging.getLogger(__name__)

Executor = Callable[[AgentKit, int, Way], Awaitable[Outcome]]

EXECUTORS: dict[str, Executor] = {
    VIA_TELEGRAM: via_telegram,
    VIA_AGGREGATOR: via_browser,
    VIA_FORM: via_browser,
    VIA_EMAIL: via_email,
}


async def apply_vacancies(kit: AgentKit, vacancy_ids: list[int]) -> None:
    """Откликнуться на каждую по очереди. Мир читается раз и доучивается по ходу."""
    world = await read_world(kit.pipeline.rs, kit.pipeline.session_factory)
    total = len(vacancy_ids)
    # Счёт с нуля, как у каналов: окно само называет место в очереди с единицы.
    for number, vacancy_id in enumerate(vacancy_ids):
        kit.pipeline.emit_progress("apply", await _title(kit, vacancy_id), number, total)
        await _apply_one(kit, world, vacancy_id)


async def _apply_one(kit: AgentKit, world: World, vacancy_id: int) -> None:
    tried: set[Way] = set()
    while await awaits_application(kit.pipeline.session_factory, vacancy_id):
        ways = [w for w in await ways_in(kit.pipeline.session_factory, world, vacancy_id) if w not in tried]
        if not ways:
            return
        way = ways[0]
        tried.add(way)
        outcome = await apply_chosen(kit, vacancy_id, way)
        # Следующий способ — только после промаха способа: прочие исходы
        # решают про вакансию, а не про способ.
        if not isinstance(outcome, Missed):
            return
        if outcome.lesson is not None:
            learn(world, outcome.lesson)


async def apply_chosen(kit: AgentKit, vacancy_id: int, way: Way) -> Outcome:
    """Один названный способ, без перебора следующих; промах — строкой в журнал.

    Сбой приложения — промах этого способа: следующий ещё может сработать, и
    обрывать из-за него весь прогон незачем. Срок человека и лимит подписки
    касаются всего прогона и уходят выше.
    """
    try:
        outcome = await EXECUTORS[way.method](kit, vacancy_id, way)
    except RUN_STOPPERS:
        raise
    except Exception:
        logger.exception("отклик на вакансию %d способом %s: сбой", vacancy_id, way.method)
        return Missed("сбой приложения")
    if outcome != "applied":
        logger.info("отклик на вакансию %d способом %s не удался: %s",
                    vacancy_id, way.method, outcome.reason)
    return outcome


async def _title(kit: AgentKit, vacancy_id: int) -> str:
    async with kit.pipeline.session_factory() as session:
        title = await session.scalar(select(Vacancy.title).where(Vacancy.id == vacancy_id))
    return title or "вакансия"
