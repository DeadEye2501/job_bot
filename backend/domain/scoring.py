"""Оценка вакансии по навыкам анкеты."""

import logging

from backend.models import ProfileSkill
from backend.payloads import ParsedVacancy

logger = logging.getLogger(__name__)


def skill_key(name: str) -> str:
    """Ключ, по которому навык анкеты узнаётся в стеке вакансии.

    Пробел по краям срезается: в анкете это опечатка ввода, а не другой
    навык. То же правило держит экран статистики — без него один и тот
    же навык считался бы там своим, а в баллах чужим.
    """
    return name.strip().casefold()


def _build_skill_level_lookup(
    skills: list[ProfileSkill],
) -> dict[str, int]:
    """``{ключ навыка: уровень}``, ключи по `skill_key`.

    ``level`` for an alias is inherited from its parent ``ProfileSkill``
    — aliases are just other spellings of the same skill and must score
    the same.

    If the user has two profile skills whose aliases overlap (shouldn't
    happen in seed data, but the schema doesn't forbid it), the LAST one
    wins — same casefold key just gets overwritten. Acceptable: this is
    user-controlled data, and we'd rather not silently aggregate. We do
    log a debug message on collision so the operator can spot a misseeded
    profile when scores look off.
    """
    out: dict[str, int] = {}

    def _put(key: str, level: int, source: str) -> None:
        prev = out.get(key)
        if prev is not None and prev != level:
            logger.debug(
                "profile skill key collision: %r already mapped to "
                "level=%d, overwritten by %s with level=%d",
                key, prev, source, level,
            )
        out[key] = level

    for s in skills:
        # Пустота проверяется по ключу, а не по сырой строке: имя из одних
        # пробелов дало бы пустой ключ, и любая пробельная строка в стеке
        # вакансии находила бы его как знакомый навык.
        if s.name and skill_key(s.name):
            _put(skill_key(s.name), s.level, f"name={s.name!r}")
        for alias in (s.aliases or []):
            if isinstance(alias, str) and skill_key(alias):
                _put(skill_key(alias), s.level, f"alias={alias!r}")
    return out


def build_skill_lookup(skills: list[ProfileSkill]) -> set[str]:
    """Ключи, по которым строка стека считается знакомой анкете.

    Выводится из `_build_skill_level_lookup`, а не собирается своим обходом:
    иначе зелёный чип в карточке и начисленный балл могли бы разойтись во
    мнении о том, что анкета знает. Уровень подсветке не нужен, ей достаточно
    самого факта. Зовут отсюда двое: окно — за зелёные чипы карточки, и
    экран статистики — за отметку «мой» у технологии.
    """
    return set(_build_skill_level_lookup(skills))


def score_parsed(
    parsed: ParsedVacancy, skills: list[ProfileSkill]
) -> int:
    """Score a vacancy based on its required/preferred stack split (LLM
    already canonicalized & deduplicated — see PARSE_VACANCY_PROMPT).

    Formula (per stack item):

    | situation                     | contribution |
    | ----------------------------- | ------------ |
    | required, profile has it      | +level       |
    | required, profile lacks it    | -1           |
    | preferred, profile has it     | +(level - 1) |
    | preferred, profile lacks it   | 0            |

    Notes:
    - "Profile has it" = case-insensitive match on profile skill name OR
      any of its aliases. LLM is instructed to map mentions to canonical
      profile names, so most matches will be on ``name``; alias-fallback
      handles the case where LLM missed the canonicalization step.
    - ``preferred`` with ``level == 1`` → +0 (formula not clamped). This
      is intentional: a desirable basic skill shouldn't bump the score
      above default.
    """
    if not skills:
        return 0
    level_lookup = _build_skill_level_lookup(skills)
    total = 0
    for item in parsed.stack_required:
        if not isinstance(item, str) or not item:
            continue
        level = level_lookup.get(skill_key(item))
        if level is None:
            total -= 1
        else:
            total += level
    for item in parsed.stack_preferred:
        if not isinstance(item, str) or not item:
            continue
        level = level_lookup.get(skill_key(item))
        if level is None:
            continue
        total += level - 1
    return total
