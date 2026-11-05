"""Запись строк «профиль × предмет»: тумблеры, отметки чтения, выбор резюме.

Общие модели отдают эти значения атрибутами только для чтения
(`models/contacts.py`, `models/settings.py`), а пишут их только отсюда.
"""

from dataclasses import dataclass

from sqlalchemy import insert, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import (
    Aggregator,
    Blacklist,
    TelegramChannel,
    WorkspaceAggregator,
    WorkspaceBlacklist,
    WorkspaceChannel,
)


@dataclass(frozen=True)
class _Switches:
    """Где лежат значения предмета в профиле и как их читает его модель."""

    model: type
    link: str
    loaded: tuple[str, ...]
    """Закрытые имена загружаемых полей: `refresh` по открытому имени гибрида
    падает `KeyError`."""
    copied: tuple[str, ...]
    """Что переносит копия профиля: тумблеры и выбор, без отметок чтения."""
    on: str
    """Колонка «включено»."""


_SWITCHES = {
    TelegramChannel: _Switches(
        WorkspaceChannel, "channel_id", ("_is_active", "_last_processed_msg_id"), ("is_active",),
        "is_active",
    ),
    Aggregator: _Switches(
        WorkspaceAggregator, "aggregator_id", ("_is_active", "_last_run_at"),
        ("is_active", "chosen_resume_id"), "is_active",
    ),
    Blacklist: _Switches(WorkspaceBlacklist, "blacklist_id", ("_active",), ("active",), "active"),
}


def switch_model(model: type) -> tuple[type, str]:
    """Таблица «профиль × предмет» модели и её колонка ссылки на предмет."""
    switches = _SWITCHES[model]
    return switches.model, switches.link


async def load_switches(session: AsyncSession, row: TelegramChannel | Aggregator | Blacklist) -> None:
    """Догрузить атрибуты профиля у строки после вставки или записи тумблера.

    У только что вставленной строки они не загружены: чтение в сессии падает
    `MissingGreenlet`, после неё — `DetachedInstanceError`.
    """
    await session.refresh(row, list(_SWITCHES[type(row)].loaded))


async def switched_on_in(
    session: AsyncSession, row: TelegramChannel | Aggregator | Blacklist
) -> list[int]:
    """Профили, в которых предмет включён."""
    switches = _SWITCHES[type(row)]
    table = switches.model
    return list((await session.scalars(
        select(table.workspace_id).where(
            getattr(table, switches.link) == row.id, getattr(table, switches.on)
        )
    )).all())


async def put_switch(
    session: AsyncSession,
    row: TelegramChannel | Aggregator | Blacklist,
    workspace_id: int,
    **values,
) -> None:
    """Записать значения предмета в профиле: завести строку профиля или поправить.

    Сделку держит зовущий.
    """
    switches = _SWITCHES[type(row)]
    switch = await session.get(switches.model, (workspace_id, row.id))
    if switch is None:
        session.add(switches.model(workspace_id=workspace_id, **{switches.link: row.id}, **values))
    else:
        for name, value in values.items():
            setattr(switch, name, value)
    await session.flush()
    await load_switches(session, row)


async def copy_switches(session: AsyncSession, source_id: int, target_id: int) -> None:
    """Перенести тумблеры и выбор резюме из профиля в профиль, без отметок чтения.

    Отметки чтения не переносятся: новый профиль читает каналы и сайты с начала,
    иначе не увидел бы ни одной уже вышедшей вакансии. Сделку держит зовущий.
    """
    for switches in _SWITCHES.values():
        table = switches.model
        names = (switches.link, *switches.copied)
        await session.execute(
            insert(table).from_select(
                ["workspace_id", *names],
                select(literal(target_id), *(getattr(table, name) for name in names))
                .where(table.workspace_id == source_id),
            )
        )
