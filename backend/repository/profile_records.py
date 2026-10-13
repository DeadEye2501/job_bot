"""Запись перечня записей анкеты со стеком — мест работы и проектов."""

import logging
from collections.abc import Callable
from typing import NamedTuple

from sqlalchemy import Table, delete
from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.skill_names import skill_key
from backend.models import ProfileSkill
from backend.repository.profile_skills import index_skill_keys, list_skills

logger = logging.getLogger(__name__)


class RowError(ValueError):
    """Строка перечня не прошла проверку.

    ``index`` — номер строки с единицы, ``problem`` — что не так, словами для
    окна: записей бывает десяток, и одинаковы они на вид, — без номера человек
    искал бы плохую глазами.
    """

    def __init__(self, index: int, problem: str) -> None:
        self.index = index
        self.problem = problem
        super().__init__(f"Запись #{index}: {problem}")


class RecordKind(NamedTuple):
    """Вид записи анкеты: модель, её связка с навыками и разбор строки окна в
    поля модели. Разбор бросает ``ValueError`` с причиной словами."""

    model: type
    links: Table
    fields_of: Callable[[dict], dict]


async def wipe_records(session: AsyncSession, kind: RecordKind) -> None:
    """Стереть записи вида вместе со связками «запись — навык».

    Порядок несущий: проверка внешних ключей у этого движка включена, и
    сотри записи первыми — база отказала бы, потому что на них ещё смотрят
    связки. Стирают записи две дороги — разбор резюме и запись из окна, — и
    порядок у них один.
    """
    await session.execute(delete(kind.links))
    await session.execute(delete(kind.model))


def _stack_by_key(rows: list[ProfileSkill]) -> dict[str, ProfileSkill]:
    """Навыки анкеты по ключу их названия; прозвища сюда не идут.

    Прозвища знает разбор резюме, потому что стек записи приходит от модели
    любым написанием. Окно же присылает выбранное из списка, то есть само
    название, и лишний ключ там только множил бы столкновения.
    """
    lookup: dict[str, ProfileSkill] = {}
    for row in rows:
        index_skill_keys(lookup, (row.name,), row, "save_records")
    return lookup


def link_stack(record, names, by_key: dict[str, ProfileSkill]) -> list[str]:
    """Связать запись с названными навыками анкеты; вернуть незнакомые названия.

    Что делать с незнакомыми, решает зовущий: окно предлагает выбирать из
    заведённых и их отбрасывает, разбор резюме жалуется в журнал.
    """
    unknown = []
    for name in [str(one) for one in names or []]:
        skill = by_key.get(skill_key(name))
        if skill is None:
            unknown.append(name)
        # Повтор отсеивается по самому навыку, а не по написанию: «Node.js» и
        # «Node JS», название и прозвище ведут к одной строке, и вторая связь
        # упала бы на первичном ключе, унося всю запись.
        elif skill not in record.skills:
            record.skills.append(skill)
    return unknown


def _parsed_rows(rows: list[dict], fields_of: Callable[[dict], dict]) -> list[tuple[dict, dict]]:
    """Проверить все строки и разобрать их в поля записи.

    Проверка идёт до первой записи в базу: сорвись она посередине, человек
    потерял бы уже введённое. Номер строки едет в отказ, чтобы окно показало
    беду там, где она есть.
    """
    checked = []
    for number, row in enumerate(rows, start=1):
        try:
            checked.append((row, fields_of(row)))
        except ValueError as e:
            raise RowError(number, str(e)) from e
    return checked


async def replace_records(
    session: AsyncSession, rows: list[dict], profile_id: int, kind: RecordKind
) -> None:
    """Заменить записи вида присланным перечнем вместе со связками стека.

    Строки пишутся в присланном порядке. Плохая строка отказывает ``RowError``
    до записи в базу. Сделку держит зовущий.
    """
    by_key = _stack_by_key(await list_skills(session))
    parsed = _parsed_rows(rows, kind.fields_of)
    await wipe_records(session, kind)
    await session.flush()
    for row, fields in parsed:
        record = kind.model(profile_id=profile_id, **fields)
        link_stack(record, row.get("skill_names"), by_key)
        session.add(record)
    await session.flush()
    logger.debug("Saved %s: %d rows", kind.model.__tablename__, len(parsed))
