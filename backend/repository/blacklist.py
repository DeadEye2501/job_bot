"""Ведение чёрного списка."""

import logging

from typing import Literal

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Blacklist, Company, HR, TelegramChannel

from backend.repository.blacklist_marks import active_mark_of
from backend.repository.channels import channel_blacklist_preferred_value
from backend.repository.companies_card import company_blacklist_preferred_value
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


def _named_candidates(named: list[tuple[str | None, str | None]]) -> list[dict]:
    """Строки списка «добавить в чёрный список» у предмета с названием.

    Принимает пары «отсеиваемое значение, название». Годится тем, у кого
    название отдельно от значения: у собеседника это имя против ника, у
    канала — заголовок против ника. Компания такой формы не имеет —
    уточнением там служит сайт, а порядок задаёт сам запрос.
    """
    out: list[dict] = []
    for value, title in named:
        if value is None:
            continue
        out.append({"value": value, "label": title or value, "sub": value if title else None})
    out.sort(key=lambda x: (x["label"] or "").casefold())
    return out


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
        return _named_candidates(
            [(hr_blacklist_preferred_value(hr), hr.name) for hr in rows]
        )
    if kind == "company":
        rows = (
            await session.scalars(select(Company).order_by(Company.name.asc()))
        ).all()
        out: list[dict] = []
        for co in rows:
            value = company_blacklist_preferred_value(co)
            if value is None:
                continue
            out.append({"value": value, "label": co.name, "sub": co.website or None})
        return out
    if kind == "channel":
        rows = (
            await session.scalars(
                select(TelegramChannel).where(TelegramChannel.username.is_not(None))
            )
        ).all()
        return _named_candidates(
            [(channel_blacklist_preferred_value(ch), ch.title) for ch in rows]
        )
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
