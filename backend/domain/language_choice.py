"""Решение, на каком языке писать — человеку или работодателю — и искать работу.

Решается здесь и только здесь. Промпты и модули, пишущие текст, язык не
выбирают — им приходит готовая строка: так правило одно, а не по копии в
каждом наставлении, и модель не угадывает его по анкете и посту каждый раз
по-своему.
"""

from collections.abc import Iterable

from backend.domain.taxonomy import CEFR_LEVELS, NATIVE_LEVEL

FALLBACK_LANGUAGE = "English"
"""Язык человека, у которого в анкете нет родного."""


def person_language(languages: Iterable) -> str:
    """Язык человека: первый родной в его списке, без родного — английский.

    На нём пишется всё, что приложение говорит самому человеку. Языки — что
    угодно с `name` и `level`.
    """
    return next((lang.name for lang in languages if lang.level == NATIVE_LEVEL), FALLBACK_LANGUAGE)


def search_languages(languages: Iterable) -> list[str]:
    """Языки, на которых искать работу: родные и те, где уровень не ниже B1;
    таких нет — язык человека.

    B1 — тот же порог, что у языка, который вакансия требует без уровня: ищи
    выше — и пропустишь вакансии, которые отбор пропустил бы.
    """
    languages = list(languages)
    usable = (NATIVE_LEVEL, *CEFR_LEVELS[CEFR_LEVELS.index("B1"):])
    return [lang.name for lang in languages if lang.level in usable] or [person_language(languages)]


def reply_language(vacancy_language: str | None, person: str) -> str:
    """Язык отклика: язык вакансии, а неизвестен он — язык человека.

    Откликом считается всё, что уходит работодателю или вводится в его форму в
    ответ на вакансию: письмо, письмо вдогон, ответы на вопросы формы.
    """
    return vacancy_language or person
