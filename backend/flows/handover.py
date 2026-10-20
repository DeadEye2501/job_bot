"""Передача отобранного откликателю: решение «откликаться» и догон новых HR после отклика."""

from dataclasses import dataclass, replace

from sqlalchemy import select

from backend.applying.world import AWAITS_APPLICATION
from backend.flows import parse
from backend.flows.dm_backfill import spawn_hr_backfill
from backend.flows.parse import Judged
from backend.models import Vacancy
from backend.repository.hr_card import LAST_VACANCY_ORDER
from backend.repository.vacancies_common import PARSED_ONLY
from backend.repository.vacancies_new import made_by_hand


@dataclass(frozen=True)
class Intake:
    """Как вести разобранную строку: из какого она канала, можно ли её снести
    как мусор и отдавать ли откликателю.

    Решает это зовущий, а не разбор и не передача: каждый знает, ручается ли он
    за текст и просили ли отклика. По умолчанию — без канала, сносить можно,
    отдавать; заведённую человеком разбор не сносит и так.
    """

    channel: str | None = None
    allow_delete: bool = True
    hands_over: bool = True


async def orphan_intake(pipeline, vacancy_id: int, intake: Intake) -> Intake:
    """Как вести брошенную недоразобранной строку: заведённую человеком — без передачи.

    Отдавать ли её откликателю, человек решал при заведении, и решение это
    жило только в окне. Дочитывают такую строку двое — подбор недоразобранного
    и обход канала, наткнувшийся на её перепост, — и правило у них одно.
    """
    async with pipeline.session_factory() as session:
        by_hand = await made_by_hand(session, vacancy_id)
    return replace(intake, hands_over=False) if by_hand else intake


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


async def hand_over(pipeline, judged: list[tuple[int, Judged]], *, applies: bool) -> None:
    """Отклик раньше догона: догон, пошедший первым, положил бы наше письмо
    в переписку без вакансии. Сорвавшийся отклик догона не отменяет: новый HR
    уже в базе, и пустая переписка у него — та же беда.

    Откликателя не зовут, если его не просил зовущий (`applies`) или выключен
    автоотклик, а догон остаётся в обоих случаях: догон — не отклик. Режим
    решается здесь, один раз на все разборы; просить ли — у зовущего, и сюда
    признаков строки не читают. Подтверждение передачи не касается: человека
    ждёт уже откликатель."""
    stored = [vacancy_id for vacancy_id, one in judged if one.stored]
    handing = applies and pipeline.rs.auto_apply != "false"
    chosen = await to_apply(pipeline.session_factory, stored) if handing else []
    try:
        if chosen:
            await pipeline.apply(chosen)
    finally:
        for _, one in judged:
            if one.fresh_hr is not None:
                spawn_hr_backfill(pipeline, one.fresh_hr)


async def judge_and_hand_over(pipeline, vacancy_id: int, text: str, intake: Intake) -> bool:
    """Разбор одной вакансии и передача её итога; ответ — записан ли исход."""
    judged = await parse.parse_and_update_vacancy(
        pipeline, vacancy_id, text, intake.channel, allow_delete=intake.allow_delete)
    await hand_over(pipeline, [(vacancy_id, judged)], applies=intake.hands_over)
    return judged.stored
