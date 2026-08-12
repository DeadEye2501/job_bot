"""Оценка вакансии по навыкам анкеты."""

import logging

from backend.domain.skill_names import index_by_key, skill_key
from backend.models import ProfileSkill
from backend.payloads import ParsedVacancy

logger = logging.getLogger(__name__)


def _build_skill_level_lookup(
    skills: list[ProfileSkill],
) -> dict[str, int]:
    """``{ключ навыка: уровень}``, ключи по `skill_key`.

    ``level`` for an alias is inherited from its parent ``ProfileSkill``
    — aliases are just other spellings of the same skill and must score
    the same.

    Два навыка с общим ключом — схема такого не запрещает — разрешаются в
    пользу первого; само правило живёт в `domain/skill_names.index_by_key`.
    Жалуемся вполголоса и только на спор уровней: одинаковый уровень под
    общим ключом баллу вакансии ничего не меняет.
    """
    out: dict[str, int] = {}
    for s in skills:
        for name, key, existing in index_by_key(
            out, (s.name, *(s.aliases or [])), s.level
        ):
            if existing != s.level:
                logger.debug(
                    "profile skill key collision: %r already mapped to "
                    "level=%d, %s %r with level=%d ignored",
                    key, existing,
                    "name" if name == s.name else "alias", name, s.level,
                )
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


def _required_points(level_lookup: dict[str, int], item: object) -> int:
    """Вклад обязательной технологии: уровень свой или штраф за чужую.

    Штраф здесь несущий: вакансия, требующая незнакомого, должна опускаться
    ниже вакансии, не требующей ничего.
    """
    if not isinstance(item, str) or not item:
        return 0
    level = level_lookup.get(skill_key(item))
    return -1 if level is None else level


def _preferred_points(level_lookup: dict[str, int], item: object) -> int:
    """Вклад желательной технологии: уровень минус единица, чужая — ноль.

    Единица вычитается нарочно: желательный навык начального уровня не
    поднимает вакансию над остальными, а незнание желательного не наказывает.
    """
    if not isinstance(item, str) or not item:
        return 0
    level = level_lookup.get(skill_key(item))
    return 0 if level is None else level - 1


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
    - "Profile has it" = ``skill_key`` match on profile skill name OR
      any of its aliases. LLM is instructed to map mentions to canonical
      profile names, so most matches will be on ``name``; alias-fallback
      handles the case where LLM missed the canonicalization step.
    - почему у желательного вычитается единица — :func:`_preferred_points`,
      почему у обязательного стоит штраф — :func:`_required_points`.
    """
    if not skills:
        return 0
    level_lookup = _build_skill_level_lookup(skills)
    return sum(
        _required_points(level_lookup, item) for item in parsed.stack_required
    ) + sum(
        _preferred_points(level_lookup, item) for item in parsed.stack_preferred
    )
