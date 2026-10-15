"""Резюме человека на сайте агрегатора — зеркало того, что сейчас на сайте.

От `aggregators.py` отличается предметом: там строка самого сайта, здесь
список его резюме со своей сверкой. Истории список не держит: что пропало с
сайта, из базы удаляется. Отметку «откликаться этим» ставит только
`choose_resume` — сверка её не ставит никогда, даже единственному резюме:
угаданное резюме может оказаться резюме другой профессии.
"""

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Aggregator, AggregatorResume
from backend.payloads import SeenResume


async def resumes_of(session: AsyncSession, aggregator_id: int) -> list[AggregatorResume]:
    """Резюме сайта в порядке сайта."""
    return list((await session.scalars(
        select(AggregatorResume)
        .where(AggregatorResume.aggregator_id == aggregator_id)
        .order_by(AggregatorResume.position)
    )).all())


async def sync_resumes(
    session: AsyncSession, aggregator_id: int, seen: list[SeenResume], can_add: bool
) -> None:
    """Привести список резюме к увиденному на сайте; резюме узнаётся по ссылке.

    Совпавшее остаётся той же записью: название, редактор и место
    переписываются, отметка цела. Новое добавляется без отметки, пропавшее удаляется вместе
    со своей. Ссылка, названная дважды, — одно резюме на первом своём месте.
    """
    known = {row.url: row for row in await resumes_of(session, aggregator_id)}
    first_seen: dict[str, SeenResume] = {}
    for item in seen:
        first_seen.setdefault(item.url, item)
    for position, item in enumerate(first_seen.values()):
        row = known.pop(item.url, None)
        if row is None:
            session.add(AggregatorResume(
                aggregator_id=aggregator_id, title=item.title, url=item.url,
                editor_url=item.editor_url, position=position,
            ))
        else:
            row.title, row.editor_url, row.position = item.title, item.editor_url, position
    for row in known.values():
        await session.delete(row)
    (await session.get(Aggregator, aggregator_id)).can_add_resume = can_add


async def forbid_more_resumes(session: AsyncSession, aggregator_id: int) -> None:
    """Сайт не дал завести ещё одно резюме: флаг «можно» снимается. Признаки
    перечня могли обмануть, а отказ сайта при создании — уже не признак, а факт."""
    (await session.get(Aggregator, aggregator_id)).can_add_resume = False


async def choose_resume(session: AsyncSession, aggregator_id: int, resume_id: int) -> None:
    """Отметить резюме «откликаться этим», сняв отметку с прежнего.

    Снятие идёт первым запросом: два отмеченных разом база не примет.
    """
    await session.execute(
        update(AggregatorResume).where(AggregatorResume.aggregator_id == aggregator_id)
        .values(is_chosen=False)
    )
    await session.execute(
        update(AggregatorResume)
        .where(AggregatorResume.id == resume_id)
        .values(is_chosen=True)
    )


async def drop_resume(session: AsyncSession, aggregator_id: int, url: str) -> None:
    """Удалить резюме, которого не оказалось на сайте. Другое вместо него не отмечается.

    Резюме узнаётся по ссылке, как при сверке, а не по отметке: пока шёл
    отклик, человек мог отметить другое — его удалять не за что.
    """
    await session.execute(
        delete(AggregatorResume)
        .where(AggregatorResume.aggregator_id == aggregator_id, AggregatorResume.url == url)
    )


async def chosen_resume(session: AsyncSession, aggregator_id: int) -> AggregatorResume | None:
    """Резюме, которым откликаться на этом сайте; пусто — человек не выбрал."""
    return await session.scalar(
        select(AggregatorResume)
        .where(AggregatorResume.aggregator_id == aggregator_id, AggregatorResume.is_chosen)
    )
