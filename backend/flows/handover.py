"""Передача отобранного откликателю: решение «откликаться» и догон новых HR после отклика."""

from sqlalchemy import select

from backend.applying.world import AWAITS_APPLICATION
from backend.flows import parse
from backend.flows.dm_backfill import spawn_hr_backfill
from backend.flows.parse import Judged
from backend.models import Vacancy
from backend.repository.hr_card import LAST_VACANCY_ORDER
from backend.repository.vacancies_common import PARSED_ONLY


async def to_apply(session_factory, vacancy_ids: list[int]) -> list[int]:
    """Что из разобранного поставить в очередь откликов: ждущее отклика после вердикта."""
    if not vacancy_ids:
        return []
    async with session_factory() as session:
        rows = await session.scalars(select(Vacancy.id).where(
            Vacancy.id.in_(vacancy_ids), AWAITS_APPLICATION))
        chosen = set(rows)
    return [vacancy_id for vacancy_id in vacancy_ids if vacancy_id in chosen]


async def new_to_apply(session_factory) -> list[int]:
    """Всё, что ждёт отклика и разобрано, свежие первыми."""
    async with session_factory() as session:
        return list(await session.scalars(
            select(Vacancy.id)
            .where(AWAITS_APPLICATION, PARSED_ONLY)
            .order_by(*LAST_VACANCY_ORDER)
        ))


async def hand_over(pipeline, judged: list[tuple[int, Judged]]) -> None:
    """Отклик раньше догона: догон, пошедший первым, положил бы наше письмо
    в переписку без вакансии. Сорвавшийся отклик догона не отменяет: новый HR
    уже в базе, и пустая переписка у него — та же беда.

    Выключенный автоотклик откликателя не зовёт, а догон оставляет: догон — не
    отклик. Решается здесь, один раз на все разборы."""
    stored = [vacancy_id for vacancy_id, one in judged if one.stored]
    chosen = await to_apply(pipeline.session_factory, stored) if pipeline.rs.auto_apply else []
    try:
        if chosen:
            await pipeline.apply(chosen)
    finally:
        for _, one in judged:
            if one.fresh_hr is not None:
                spawn_hr_backfill(pipeline, one.fresh_hr)


async def judge_and_hand_over(pipeline, vacancy_id: int, text: str, channel_username: str | None,
                              *, allow_delete: bool = True) -> bool:
    """Разбор одной вакансии и передача её итога; ответ — записан ли исход."""
    judged = await parse.parse_and_update_vacancy(
        pipeline, vacancy_id, text, channel_username, allow_delete=allow_delete)
    await hand_over(pipeline, [(vacancy_id, judged)])
    return judged.stored
