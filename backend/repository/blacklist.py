"""Ведение чёрного списка."""

import logging

from typing import Literal

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Blacklist, Company, HR, TelegramChannel

from backend.repository.channels import channel_blacklist_preferred_value
from backend.repository.hr_card import hr_blacklist_preferred_value

logger = logging.getLogger(__name__)

BlacklistOutcome = Literal["created", "reactivated", "already_active"]


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


_BLACKLIST_FIELD_UNSET = object()


class BlacklistUpdateError(ValueError):
    """Soft-validation ошибка inline-edit'а blacklist'а."""


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

    Raises ``BlacklistUpdateError`` если value передан и оказался пустой
    после strip — пустое value семантически бесполезно (никогда ни с чем
    не совпадёт), плюс пользователь не сможет визуально отличить
    очищенный ряд от placeholder'а.

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
        normalized_value = (value or "").strip()
        if not normalized_value:
            raise BlacklistUpdateError("Значение не может быть пустым.")
        row.value = normalized_value
    if reason is not _BLACKLIST_FIELD_UNSET:
        normalized_reason = (reason or "").strip()
        row.reason = normalized_reason or None
    return True


async def create_blacklist(
    session: AsyncSession,
    *,
    kind: str,
    value: str,
    reason: str | None = None,
) -> tuple[Blacklist, BlacklistOutcome]:
    """Insert a blacklist row, дедупликация по (kind, value).

    Если строка с теми же (kind, value) уже есть:
    - active=True → возвращаем её как есть, "already_active"
    - active=False → ре-активируем и возвращаем, "reactivated"

    Иначе вставляем новую с active=True, "created".

    Исход назван словом, а не признаком «завели ли»: карточка HR, компании
    и канала говорит о трёх случаях по-разному («добавлен», «возвращён»,
    «уже в списке»), и признаком из двух значений средний не выражается.
    Экран чёрного списка читает из этого только «завели ли» — ему хватало
    и прежнего признака.

    Returns (row, outcome). Caller wraps in ``session.begin()``.
    """
    normalized_value = (value or "").strip()
    if not normalized_value:
        raise BlacklistUpdateError("Значение не может быть пустым.")
    normalized_kind = (kind or "").strip()
    if not normalized_kind:
        raise BlacklistUpdateError("Тип обязателен.")
    normalized_reason = (reason or "").strip() if reason is not None else None
    if normalized_reason == "":
        normalized_reason = None

    existing = (
        await session.scalars(
            select(Blacklist).where(
                Blacklist.kind == normalized_kind,
                Blacklist.value == normalized_value,
            )
        )
    ).first()
    if existing is not None:
        outcome: BlacklistOutcome = "already_active"
        if not existing.active:
            existing.active = True
            outcome = "reactivated"
            logger.info(
                "Blacklist reactivated id=%d kind=%s value=%r",
                existing.id,
                normalized_kind,
                normalized_value,
            )
        if normalized_reason and not existing.reason:
            existing.reason = normalized_reason
        return existing, outcome

    row = Blacklist(
        kind=normalized_kind,
        value=normalized_value,
        reason=normalized_reason,
        active=True,
    )
    session.add(row)
    await session.flush()
    logger.info(
        "Blacklist created id=%d kind=%s value=%r reason=%r",
        row.id,
        normalized_kind,
        normalized_value,
        normalized_reason,
    )
    return row, "created"


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


async def list_blacklist_candidates(
    session: AsyncSession, kind: str
) -> list[dict]:
    """Список options для combobox'а add-modal'а blacklist'а.

    Returns: [{value, label, sub?}], отсортировано по label.

    - kind="hr": HRs с @username или telegram_user_id (что-то для
      сохранения как blacklist value).
    - kind="company": все компании by name.
    - kind="channel": каналы с @username.
    - kind="keyword": [] (свободный ввод).
    """
    if kind == "hr":
        rows = (
            await session.scalars(
                select(HR).where(
                    or_(HR.telegram_username.is_not(None), HR.telegram_user_id.is_not(None))
                )
            )
        ).all()
        out: list[dict] = []
        for hr in rows:
            value = hr_blacklist_preferred_value(hr)
            if value is None:
                continue
            label = hr.name or value
            sub = value if hr.name else None
            out.append({"value": value, "label": label, "sub": sub})
        out.sort(key=lambda x: (x["label"] or "").casefold())
        return out
    if kind == "company":
        rows = (
            await session.scalars(select(Company).order_by(Company.name.asc()))
        ).all()
        return [
            {"value": co.name, "label": co.name, "sub": co.website or None}
            for co in rows if co.name
        ]
    if kind == "channel":
        rows = (
            await session.scalars(
                select(TelegramChannel).where(TelegramChannel.username.is_not(None))
            )
        ).all()
        out = []
        for ch in rows:
            value = channel_blacklist_preferred_value(ch)
            if value is None:
                continue
            label = ch.title or value
            sub = value if ch.title else None
            out.append({"value": value, "label": label, "sub": sub})
        out.sort(key=lambda x: (x["label"] or "").casefold())
        return out
    return []


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


async def load_active_blacklist_patterns(
    session: AsyncSession,
) -> list[str]:
    return list(
        (
            await session.scalars(
                select(Blacklist.value).where(Blacklist.active)
            )
        ).all()
    )
