"""Ведение чёрного списка."""

import logging

from typing import Literal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Blacklist
from backend.payloads import text_or_none

from backend.repository import channels
from backend.repository.blacklist_marks import active_mark_of

logger = logging.getLogger(__name__)

BlacklistOutcome = Literal["created", "reactivated", "already_active"]
"""Чем кончилось добавление в список.

Исход назван словом, а не признаком «завели ли»: карточка HR, компании и
канала говорит о трёх случаях по-разному («добавлен», «возвращён», «уже в
списке»), и признаком из двух значений средний не выражается. Экран чёрного
списка читает из этого только «завели ли» — ему хватало и прежнего признака.
"""


async def _hold_the_channel_rule(session: AsyncSession, kind: str) -> None:
    """Держать правило «канал в отсеве не работает» при каждой записи отметки.

    Состояния несовместимы: канал, попавший в отсев, не должен опрашиваться.
    Прежде это правило звали три дороги из пяти — карточка канала, заведение
    записи с экрана списка и самопочинка на показе, — а тумблер строки и
    правка её значения не звали, и отсеянный канал продолжал носить вакансии
    до ближайшего открытия списка.

    Зов стоит здесь, у самой записи, чтобы забыть о нём не мог никто.
    """
    if kind == "channel":
        await channels.deactivate_blacklisted_channels(session)


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
    if row.active:
        await _hold_the_channel_rule(session, row.kind)
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


async def rename_blacklist_marks(
    session: AsyncSession, kind: str, *, old_value: str, new_value: str
) -> None:
    """Перевести действующие отметки предмета на его новое написание.

    Предмет опознают написанием, а оно сменяемое: компанию переименовывают в
    карточке, и её имя перестаёт быть именем при слиянии. Останься строка на
    прежнем написании — она продолжила бы отсеивать посты, а с карточки
    пропала бы: та ищет отметку по нынешнему написанию.

    Строка под новым написанием уже бывает заведена — так сливают две
    отмеченные записи. Тогда действующей становится она, а переезжающие
    гаснут: второй строки с тем же написанием не допускает и заведение, а
    погашенная остаётся видимой на экране списка. Транзакцию закрывает
    зовущий.
    """
    if old_value == new_value:
        return
    moving = (
        await session.scalars(
            select(Blacklist).where(active_mark_of(kind, [old_value]))
        )
    ).all()
    if not moving:
        return
    standing = await _same_entry(session, kind, new_value)
    for row in moving:
        if standing is None:
            row.value = new_value
            standing = row
        else:
            row.active = False
    standing.active = True
    await _hold_the_channel_rule(session, kind)
    logger.info(
        "Blacklist marks of kind=%s moved %r -> %r (rows=%d)",
        kind,
        old_value,
        new_value,
        len(moving),
    )


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


async def _free_value(session: AsyncSession, row: Blacklist, value: str) -> str:
    """Значение, если им не занята другая строка того же рода; иначе отказ.

    Род входит в сравнение: компанию и человека зовут одинаково чаще, чем
    кажется, а отметку каждый экран ищет своим родом.
    """
    twin = await _same_entry(session, row.kind, value)
    if twin is not None and twin.id != row.id:
        raise BlacklistUpdateError(f"Запись «{value}» уже есть в списке.")
    return value


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

    Raises ``BlacklistUpdateError`` и на значении, занятом другой строкой
    того же рода: заведение двойника не допускает — повторное «в отсев»
    поднимает найденную строку вместо второй, — и правка не может быть
    дорогой в обход. Два ряда с одним написанием человек гасил бы по одному,
    не понимая, почему отметка не снимается.

    Returns False if the row is missing. Caller wraps in
    ``session.begin()``.
    """
    row = await session.get(Blacklist, blacklist_id)
    if row is None:
        return False
    if value is not _BLACKLIST_FIELD_UNSET:
        row.value = await _free_value(session, row, _required_value(value))
        await _hold_the_channel_rule(session, row.kind)
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

    Канальную строку сопровождает гашение самих каналов — см.
    `_hold_the_channel_rule`.

    Returns (row, outcome). Caller wraps in ``session.begin()``.
    """
    normalized_value = _required_value(value)
    normalized_kind = (kind or "").strip()
    if not normalized_kind:
        raise BlacklistUpdateError("Тип обязателен.")
    normalized_reason = text_or_none(reason)

    existing = await _same_entry(session, normalized_kind, normalized_value)
    if existing is not None:
        row, outcome = existing, _reuse_existing(existing, normalized_reason)
    else:
        row, outcome = await _insert_blacklist(
            session, normalized_kind, normalized_value, normalized_reason
        ), "created"
    await _hold_the_channel_rule(session, normalized_kind)
    return row, outcome


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
