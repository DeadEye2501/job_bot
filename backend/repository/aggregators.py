"""Ведение записей об агрегаторах."""

from datetime import datetime

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.hosts import normalize_host
from backend.models import Aggregator, Application, TrashEvent, Vacancy
from backend.repository.vacancies_life import repoint_vacancies

WEB_SEARCH_NAME = "Поиск по сети"


async def create_aggregator(session: AsyncSession, address: str) -> tuple[Aggregator | None, str]:
    """Завести агрегатор по адресу, набранному как угодно. Новый выключен и без входа."""
    host = normalize_host(address)
    if not host:
        return None, "invalid"
    known = await session.scalar(select(Aggregator).where(Aggregator.host == host))
    if known is not None:
        return known, "exists"
    row = Aggregator(name=host, host=host, is_active=False, is_logged_in=False)
    session.add(row)
    await session.flush()
    return row, "created"


async def list_aggregators(session: AsyncSession) -> list[Aggregator]:
    """Все источники-агрегаторы: «Поиск по сети» первым, дальше в порядке заведения."""
    return list((await session.scalars(
        select(Aggregator).order_by(Aggregator.host.is_not(None), Aggregator.id)
    )).all())


async def set_aggregator_active(session: AsyncSession, aggregator_id: int, active: bool) -> str:
    row = await session.get(Aggregator, aggregator_id)
    if row is None:
        return "missing"
    if active and not row.is_logged_in:
        return "not_logged_in"
    row.is_active = active
    return "ok"


async def set_logged_in(session: AsyncSession, aggregator_id: int, logged_in: bool) -> None:
    """Отметка входа. Включённость не трогает: без входа агрегатор просто не обходится."""
    row = await session.get(Aggregator, aggregator_id)
    if row is not None and row.host is not None:
        row.is_logged_in = logged_in


async def mark_run(session: AsyncSession, aggregator_id: int, started_at: datetime) -> None:
    row = await session.get(Aggregator, aggregator_id)
    if row is not None:
        row.last_run_at = started_at


async def applications_of(session: AsyncSession, aggregator_id: int) -> int:
    """Откликов, связанных с агрегатором, — их число окно называет перед удалением.

    Свои — и по вакансиям с него, и отклики его кнопкой на вакансии из других
    источников.
    """
    return int(await session.scalar(
        select(func.count(Application.id))
        .join(Vacancy, Vacancy.id == Application.vacancy_id)
        .where(or_(Vacancy.source_aggregator_id == aggregator_id,
                   Application.aggregator_id == aggregator_id))
    ) or 0)


async def delete_aggregator(session: AsyncSession, aggregator_id: int) -> str:
    """Удалить агрегатор. Вакансии, отклики и отметки о мусоре остаются, ссылка на него — нет.

    Ссылки обнуляет код: правила «обнулить при удалении» у внешних ключей нет.
    Вакансии отвязывает общее `repoint_vacancies`; отклики и мусор — другие
    таблицы, и у каждой свой запрос: обобщать `repoint_vacancies` на любую
    модель его докстрока запрещает.
    """
    block = await deletion_block(session, aggregator_id)
    if block is not None:
        return block
    row = await session.get(Aggregator, aggregator_id)
    await repoint_vacancies(
        session, Vacancy.source_aggregator_id, absorbed_id=aggregator_id, survivor_id=None
    )
    await session.execute(
        update(Application).where(Application.aggregator_id == aggregator_id)
        .values(aggregator_id=None)
    )
    await session.execute(
        update(TrashEvent).where(TrashEvent.source_aggregator_id == aggregator_id)
        .values(source_aggregator_id=None)
    )
    await session.delete(row)
    return "ok"


async def deletion_block(session: AsyncSession, aggregator_id: int) -> str | None:
    """Почему агрегатор не удалить: `missing` — его нет, `protected` — это «Поиск по сети»."""
    row = await session.get(Aggregator, aggregator_id)
    if row is None:
        return "missing"
    return "protected" if row.host is None else None


async def round_sources(session: AsyncSession) -> list[Aggregator]:
    """Источники общего обхода: включённые агрегаторы со входом, затем «Поиск по сети»."""
    rows = (await session.scalars(
        select(Aggregator)
        .where(Aggregator.is_active.is_(True), Aggregator.is_logged_in.is_(True))
        .order_by(Aggregator.host.is_(None), Aggregator.id)
    )).all()
    return list(rows)
