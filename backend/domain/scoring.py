"""Оценка вакансии по навыкам анкеты."""

import logging

from backend.domain.skill_names import index_by_key, skill_key
from backend.models import ProfileSkill

logger = logging.getLogger(__name__)


def _build_skill_level_lookup(
    skills: list[ProfileSkill],
) -> dict[str, tuple[str, int]]:
    """``{ключ написания: (ключ навыка, уровень)}``, ключи по `skill_key`.

    ``level`` for an alias is inherited from its parent ``ProfileSkill``
    — aliases are just other spellings of the same skill and must score
    the same.

    Рядом с уровнем едет ключ самого навыка — по нему видно, что два
    написания принадлежат одному умению анкеты. Без него «Photoshop» и
    «Illustrator» выглядели бы двумя навыками, и вакансия платила бы за одно
    умение дважды.

    Два навыка с общим ключом — схема такого не запрещает — разрешаются в
    пользу первого; само правило живёт в `domain/skill_names.index_by_key`.
    Жалуемся вполголоса и только на спор уровней: одинаковый уровень под
    общим ключом баллу вакансии ничего не меняет.
    """
    out: dict[str, tuple[str, int]] = {}
    for s in skills:
        owner = skill_key(s.name)
        for name, key, existing in index_by_key(
            out, (s.name, *(s.aliases or [])), (owner, s.level)
        ):
            if existing[1] != s.level:
                logger.debug(
                    "profile skill key collision: %r already mapped to "
                    "level=%d, %s %r with level=%d ignored",
                    key, existing[1],
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


def _paid_level(
    level_lookup: dict[str, tuple[str, int]], item: object, paid: set[str]
) -> int | None:
    """Уровень навыка анкеты, если он назван и ещё не оплачен.

    ``None`` — либо название анкете незнакомо, либо за этот навык уже
    заплатили: инструменты объявление называет порознь, а умение за ними
    стоит одно, и платить за него на каждое написание значило бы поднимать
    вакансию с одним знакомым умением над той, где их правда несколько.
    """
    if not isinstance(item, str) or not item:
        return None
    found = level_lookup.get(skill_key(item))
    if found is None or found[0] in paid:
        return None
    paid.add(found[0])
    return found[1]


def _required_points(
    level_lookup: dict[str, tuple[str, int]], item: object, paid: set[str]
) -> int:
    """Вклад обязательной технологии: уровень свой или штраф за чужую.

    Штраф здесь несущий: вакансия, требующая незнакомого, должна опускаться
    ниже вакансии, не требующей ничего. Незнакомые между собой не сводятся —
    общего умения за ними нет, и каждое стоит своего штрафа.
    """
    if not isinstance(item, str) or not item:
        return 0
    if skill_key(item) not in level_lookup:
        return -1
    level = _paid_level(level_lookup, item, paid)
    return 0 if level is None else level


def _preferred_points(
    level_lookup: dict[str, tuple[str, int]], item: object, paid: set[str]
) -> int:
    """Вклад желательной технологии: уровень минус единица, чужая — ноль.

    Единица вычитается нарочно: желательный навык начального уровня не
    поднимает вакансию над остальными, а незнание желательного не наказывает.
    """
    level = _paid_level(level_lookup, item, paid)
    return 0 if level is None else level - 1


def score_stack(
    stack_required: list[str],
    stack_preferred: list[str],
    skills: list[ProfileSkill],
) -> int:
    """Score a vacancy based on its required/preferred stack split.

    Половинами, а не целой разобранной вакансией: половины есть у обоих
    заводящих, а разбор поста — только у одного. Считай набранное руками
    вторым правилом рядом, и одна и та же вакансия получала бы два разных
    балла, смотря кем заведена.

    Formula (per stack item):

    | situation                     | contribution |
    | ----------------------------- | ------------ |
    | required, profile has it      | +level       |
    | required, profile lacks it    | -1           |
    | preferred, profile has it     | +(level - 1) |
    | preferred, profile lacks it   | 0            |

    Notes:
    - "Profile has it" = ``skill_key`` match on profile skill name OR any of
      its aliases. Инструменты объявление перечисляет порознь, и в стеке они
      порознь остаются — карточка обязана показать, чего именно ждут.
    - **За умение анкеты платят один раз.** Обязательная половина считается
      первой нарочно: назван навык в обеих — весит по строгой.
    - почему у желательного вычитается единица — :func:`_preferred_points`,
      почему у обязательного стоит штраф — :func:`_required_points`.
    """
    if not skills:
        return 0
    level_lookup = _build_skill_level_lookup(skills)
    paid: set[str] = set()
    required = sum(
        _required_points(level_lookup, item, paid) for item in stack_required
    )
    return required + sum(
        _preferred_points(level_lookup, item, paid) for item in stack_preferred
    )
