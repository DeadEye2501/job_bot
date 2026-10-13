"""Навыки, названные в анкете кандидата."""

import logging

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.skill_names import index_by_key
from backend.incoming import str_list
from backend.models import STACK_LINKS, ProfileSkill

logger = logging.getLogger(__name__)


def index_skill_keys(
    lookup: dict[str, ProfileSkill],
    names: tuple[str, ...],
    row: ProfileSkill,
    where: str,
) -> None:
    """Записать строку навыка под ключи её написаний; первая выигрывает.

    Само правило живёт в `domain/skill_names.index_by_key`; здесь остаётся
    жалоба. Жалуемся громко и только на спор двух разных строк: в анкете
    такого быть не должно, а схема не запрещает. Столкновение написания с
    собственным названием строки — не спор, а обычное дело.
    """
    for _name, key, existing in index_by_key(lookup, names, row):
        if existing is not row:
            logger.warning(
                "%s: skill key %r collides between %r and %r, keeping first",
                where, key, existing.name, row.name,
            )


async def list_skills(session: AsyncSession) -> list[ProfileSkill]:
    """All ProfileSkill rows ordered by id (preserves user-set order).

    Порядок здесь не украшение: столкновение ключей навыков разрешается в
    пользу первого (`domain/skill_names.index_by_key`), и без `order_by`
    «первый» назначал бы читатель, ничем этого не обещавший.
    """
    return list(
        (await session.scalars(select(ProfileSkill).order_by(ProfileSkill.id))).all()
    )


def _skill_columns(row: dict) -> dict | None:
    """Поля навыка из строки окна; пусто — в строке нет названия.

    Уровень, пришедший не числом, считается первым: анкету правит человек, и
    опечатка в поле не повод отказать ему в записи всей строки.
    """
    name = (row.get("name") or "").strip()
    if not name:
        return None
    try:
        level = int(row.get("level") or 1)
    except (TypeError, ValueError):
        level = 1
    return {
        "category": (row.get("category") or "Общее").strip() or "Общее",
        "name": name,
        "level": level,
        "aliases": str_list(row.get("aliases")),
    }


def _upsert_skills(
    session: AsyncSession, rows: list[dict], existing: dict, profile_id: int
) -> set[int]:
    """Записать присланные навыки; отдать номера уцелевших строк.

    Строка с известным номером правится на месте — так связки «место работы
    — навык» переживают даже переименование навыка. Всё остальное заводится
    заново.
    """
    keep_ids: set[int] = set()
    for row in rows:
        columns = _skill_columns(row)
        if columns is None:
            continue
        rid = row.get("id")
        rid_int = rid if isinstance(rid, int) else None
        if rid_int is not None and rid_int in existing:
            s = existing[rid_int]
            s.category = columns["category"]
            s.name = columns["name"]
            s.level = columns["level"]
            s.aliases = columns["aliases"]
            keep_ids.add(rid_int)
        else:
            session.add(ProfileSkill(profile_id=profile_id, **columns))
    return keep_ids


async def _drop_skills(
    session: AsyncSession, existing: dict, drop_ids: set[int]
) -> None:
    """Снести навыки, которых человек в анкете не оставил, сняв их со стека
    каждой записи анкеты (`STACK_LINKS`)."""
    for sid in drop_ids:
        for links in STACK_LINKS:
            await session.execute(delete(links).where(links.c.skill_id == sid))
        await session.delete(existing[sid])


async def save_skills(
    session: AsyncSession,
    rows: list[dict],
    profile_id: int,
) -> None:
    """Сохранить навыки по номерам строк, не порвав стеки мест работы и проектов.

    Строка с целым ``id`` правится на месте, без него (или с номером-строкой)
    заводится заново. Не названные в присланном перечне удаляются вместе со
    связками стека. Правка не меняет номер строки, поэтому стеки переживают и
    переименование навыка.

    Сделку держит зовущий.
    """
    existing = {s.id: s for s in await list_skills(session)}
    keep_ids = _upsert_skills(session, rows, existing, profile_id)
    drop_ids = set(existing.keys()) - keep_ids
    await _drop_skills(session, existing, drop_ids)
    await session.flush()
    logger.debug(
        "Saved skills: kept=%d dropped=%d", len(keep_ids), len(drop_ids)
    )
