"""Цикл откликателя: по каждой вакансии первый доступный способ, пока один не удастся."""

import logging
from collections.abc import Awaitable, Callable

from sqlalchemy import select

from backend.agent.kit import AgentKit
from backend.agent.sessions import HumanTimeout, LimitExhausted
from backend.applying.result import Missed, Outcome
from backend.applying.world import learn, read_world, ways_in
from backend.domain.apply_order import Way, World
from backend.models import Vacancy

logger = logging.getLogger(__name__)

Executor = Callable[[AgentKit, int, Way], Awaitable[Outcome]]

EXECUTORS: dict[str, Executor] = {}


async def apply_vacancies(kit: AgentKit, vacancy_ids: list[int]) -> None:
    """Откликнуться на каждую по очереди. Мир читается раз и доучивается по ходу."""
    world = await read_world(kit)
    total = len(vacancy_ids)
    for number, vacancy_id in enumerate(vacancy_ids, 1):
        kit.pipeline.emit_progress("apply", await _title(kit, vacancy_id), number, total)
        await _apply_one(kit, world, vacancy_id)


async def apply_chosen(kit: AgentKit, vacancy_id: int, way: Way) -> Outcome:
    """Ручной отклик: перечень — один выбранный способ."""
    return await _try(kit, vacancy_id, way)


async def _apply_one(kit: AgentKit, world: World, vacancy_id: int) -> None:
    tried: set[Way] = set()
    while True:
        ways = [w for w in await ways_in(kit, world, vacancy_id) if w not in tried]
        if not ways:
            return
        way = ways[0]
        tried.add(way)
        outcome = await _try(kit, vacancy_id, way)
        if outcome == "applied":
            return
        if outcome.lesson is not None:
            learn(world, outcome.lesson)


async def _try(kit: AgentKit, vacancy_id: int, way: Way) -> Outcome:
    """Один способ; промах — строкой в журнал.

    Сбой приложения — промах этого способа: следующий ещё может сработать, и
    обрывать из-за него весь прогон незачем. Срок человека и лимит подписки
    касаются всего прогона и уходят выше.
    """
    try:
        outcome = await EXECUTORS[way.method](kit, vacancy_id, way)
    except (HumanTimeout, LimitExhausted):
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
