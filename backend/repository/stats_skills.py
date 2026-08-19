"""Частота технологий в объявлениях за выбранный срок."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.scoring import build_skill_lookup
from backend.domain.skill_names import skill_key
from backend.models import Vacancy
from backend.repository.profile import list_skills
from backend.repository.stats_common import parsed_in_window, stats_period_since


def _count_stack_tags(stacks) -> tuple[dict[str, int], dict[str, str]]:
    """Частота технологий по канону и написание, под которым их показывать.

    Частота считается по ключу `skill_key` — одна технология даёт один
    счётчик, как бы её ни написали («Python» / «python» / «PYTHON»,
    «Docker-Compose» / «docker compose»). Внутри одной вакансии повтор не
    считается дважды. Показывается первое встреченное написание.
    """
    counts: dict[str, int] = {}
    canon_by_key: dict[str, str] = {}
    for stack in stacks:
        if not isinstance(stack, list):
            continue
        seen_in_row: set[str] = set()
        for item in stack:
            if not isinstance(item, str):
                continue
            tag = item.strip()
            # Пустое и написанное одними разделителями («///») технологией не
            # считается: ключ у такого пустой, и своей строки в списке оно не
            # получает.
            key = skill_key(tag)
            if not key:
                continue
            if key in seen_in_row:
                continue
            seen_in_row.add(key)
            canon_by_key.setdefault(key, tag)
            counts[key] = counts.get(key, 0) + 1
    return counts, canon_by_key


def _skill_items(
    counts: dict[str, int], canon_by_key: dict[str, str],
    profile_set, min_count: int,
) -> list[dict]:
    """Строки списка технологий: частые сверху, редкие отсеяны.

    Отсев по `min_count` — против шума: технология, встреченная однажды, о
    рынке не говорит ничего. При равной частоте порядок решает написание,
    приведённое `casefold`, — иначе «python» и «Python» стояли бы по разные
    стороны списка из-за одного регистра.
    """
    items = [
        {"label": canon_by_key[key], "count": cnt, "mine": key in profile_set}
        for key, cnt in counts.items()
        if cnt >= min_count
    ]
    items.sort(key=lambda it: (-it["count"], it["label"].casefold()))
    return items


async def get_stats_skills(
    session: AsyncSession, *, period: str, limit: int = 27, min_count: int = 2,
) -> dict:
    """Топ-N технологий из `Vacancy.stack` за period с маркировкой
    «есть в моём профиле».

    Как считается частота — :func:`_count_stack_tags`, как собирается сам
    список — :func:`_skill_items`. `mine` — ключ технологии среди ключей
    названий и прозвищ всех `ProfileSkill`.
    """
    base_filter = [
        *parsed_in_window(stats_period_since(period)),
        Vacancy.stack.is_not(None),
    ]

    # Тот же ключ, что и у баллов: иначе один навык считался бы здесь
    # своим, а в оценке вакансии чужим. И тот же читатель анкеты — иначе
    # «свой» на этом экране решался бы по своему набору строк.
    profile_set = build_skill_lookup(await list_skills(session))

    stacks = (
        await session.scalars(select(Vacancy.stack).where(*base_filter))
    ).all()
    counts, canon_by_key = _count_stack_tags(stacks)
    items = _skill_items(counts, canon_by_key, profile_set, min_count)
    return {
        "period": period,
        "min_count": min_count,
        "skills": items[:limit],
    }
