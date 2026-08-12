"""Ведение чёрного списка."""

import logging

from typing import Literal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Blacklist
from backend.payloads import text_or_none

from backend.repository.blacklist_marks import active_mark_of

logger = logging.getLogger(__name__)

BlacklistOutcome = Literal["created", "reactivated", "already_active"]
"""Чем кончилось добавление в список.

Исход назван словом, а не признаком «завели ли»: карточка HR, компании и
канала говорит о трёх случаях по-разному («добавлен», «возвращён», «уже в
списке»), и признаком из двух значений средний не выражается. Экран чёрного
списка читает из этого только «завели ли» — ему хватало и прежнего признака.
"""


async def set_blacklist_active(
    session: AsyncSession, blacklist_id: int, active: bool
) -> bool:
    """Toggle Blacklist.active. Returns False if the row is missing.
    Caller wraps in ``session.begin()``.
    """
    row = await session.get(Blacklist, blacklist_id)
    if row is None:
        return False
    prev = row.active
    row.active = bool(active)
    if prev != row.active:
        logger.info(
            "Blacklist %d active %s -> %s (kind=%s value=%r)",
            blacklist_id,
            prev,
            row.active,
            row.kind,
            row.value,
        )
    return True


async def deactivate_blacklist_values(
    session: AsyncSession, kind: str, candidates: list[str]
) -> int:
    """Погасить активные строки этого рода под любым из написаний предмета.

    Отдаёт число погашенных: окно по нему отличает «убрали» от «нечего
    было убирать». Строки не удаляются — решение остаётся видимым на
    экране чёрного списка с выключенной отметкой, и его можно вернуть.

    Написаний у предмета бывает несколько сразу (у HR ник и номер учётной
    записи), и гасить надо все: оставшееся держало бы отметку дальше.

    Что считать отметкой, объявлено один раз — в `active_mark_of`, откуда
    его берёт и чтение отметки для чипа карточки.

    Транзакцию закрывает зовущий.
    """
    done = await session.execute(
        update(Blacklist)
        .where(active_mark_of(kind, candidates))
        .values(active=False)
    )
    return done.rowcount or 0


_BLACKLIST_FIELD_UNSET = object()


class BlacklistUpdateError(ValueError):
    """Soft-validation ошибка inline-edit'а blacklist'а."""


def _required_value(value) -> str:
    """Значение строки без пробелов по краям; пустое — отказ.

    Пустое значение бесполезно: оно никогда ни с чем не совпадёт, а в списке
    очищенный ряд не отличить от заготовки. Отказывают обе дороги — заведение
    и правка на месте, — и одним текстом: человек видит один и тот же экран.
    """
    normalized = (value or "").strip()
    if not normalized:
        raise BlacklistUpdateError("Значение не может быть пустым.")
    return normalized


async def update_blacklist(
    session: AsyncSession,
    blacklist_id: int,
    *,
    value=_BLACKLIST_FIELD_UNSET,
    reason=_BLACKLIST_FIELD_UNSET,
) -> bool:
    """Partial update for value/reason. Sentinel `_BLACKLIST_FIELD_UNSET`
    отличает «не передали» от «передали None» — `reason` может быть
    NULL'ом (пустая причина), и UI должен иметь возможность это сохранить.

    Raises ``BlacklistUpdateError`` на пустом значении — почему, сказано
    у `_required_value`.

    Returns False if the row is missing. Caller wraps in
    ``session.begin()``.

    TODO: дедуп с другими активными рядами того же `kind` — сейчас можно
    инлайн-эдитом сделать (kind=hr, value=@x) дублем, хотя заведение
    (`create_blacklist`) этого не даёт. Добавить
    проверку `select(...).where(kind == row.kind, value == new_value,
    id != row.id)` и кидать ``BlacklistUpdateError("Уже существует")``.
    """
    row = await session.get(Blacklist, blacklist_id)
    if row is None:
        return False
    if value is not _BLACKLIST_FIELD_UNSET:
        row.value = _required_value(value)
    if reason is not _BLACKLIST_FIELD_UNSET:
        row.reason = text_or_none(reason)
    return True


async def _same_entry(
    session: AsyncSession, kind: str, value: str
) -> Blacklist | None:
    """Уже заведённая строка с тем же родом и значением."""
    return (
        await session.scalars(
            select(Blacklist).where(
                Blacklist.kind == kind, Blacklist.value == value
            )
        )
    ).first()


def _reuse_existing(existing: Blacklist, reason: str | None) -> BlacklistOutcome:
    """Поднять уже заведённую строку и сказать, чем это кончилось.

    Снятая строка возвращается в список, поднятая остаётся как была.
    Причина дописывается только в пустое: у строки, заведённой раньше,
    объяснение уже своё, и затирать его новым нельзя.
    """
    outcome: BlacklistOutcome = "already_active"
    if not existing.active:
        existing.active = True
        outcome = "reactivated"
        logger.info(
            "Blacklist reactivated id=%d kind=%s value=%r",
            existing.id,
            existing.kind,
            existing.value,
        )
    if reason and not existing.reason:
        existing.reason = reason
    return outcome


async def _insert_blacklist(
    session: AsyncSession, kind: str, value: str, reason: str | None
) -> Blacklist:
    """Завести новую строку списка — сразу действующую."""
    row = Blacklist(kind=kind, value=value, reason=reason, active=True)
    session.add(row)
    await session.flush()
    logger.info(
        "Blacklist created id=%d kind=%s value=%r reason=%r",
        row.id,
        kind,
        value,
        reason,
    )
    return row


async def create_blacklist(
    session: AsyncSession,
    *,
    kind: str,
    value: str,
    reason: str | None = None,
) -> tuple[Blacklist, BlacklistOutcome]:
    """Insert a blacklist row, дедупликация по (kind, value).

    Если строка с теми же (kind, value) уже есть — она и возвращается, с
    исходом от :func:`_reuse_existing`; иначе вставляется новая, активная.

    Returns (row, outcome). Caller wraps in ``session.begin()``.
    """
    normalized_value = _required_value(value)
    normalized_kind = (kind or "").strip()
    if not normalized_kind:
        raise BlacklistUpdateError("Тип обязателен.")
    normalized_reason = text_or_none(reason)

    existing = await _same_entry(session, normalized_kind, normalized_value)
    if existing is not None:
        return existing, _reuse_existing(existing, normalized_reason)
    return await _insert_blacklist(
        session, normalized_kind, normalized_value, normalized_reason
    ), "created"


async def delete_blacklist(
    session: AsyncSession, blacklist_id: int
) -> bool:
    """Delete a blacklist row. Returns False if the row is missing.
    Blacklist — leaf-таблица, никаких FK на неё; delete простой.
    Caller wraps в ``session.begin()``.
    """
    row = await session.get(Blacklist, blacklist_id)
    if row is None:
        return False
    logger.info(
        "Blacklist deleted id=%d kind=%s value=%r",
        blacklist_id,
        row.kind,
        row.value,
    )
    await session.delete(row)
    return True


async def list_blacklist(session: AsyncSession) -> list[Blacklist]:
    """Все строки blacklist'а одним запросом — список обычно <100, нет
    смысла гонять SQL-фильтры. UI фильтрует локально по kind и поиску.

    Order: insertion order (id ASC). Раньше сортировали по active+created
    desc — но при toggle активности ряд прыгал между верхом и низом, что
    путало пользователя. Стабильный порядок по id важнее визуальной
    группировки.
    """
    rows = (
        await session.scalars(
            select(Blacklist).order_by(Blacklist.id.asc())
        )
    ).all()
    return list(rows)
