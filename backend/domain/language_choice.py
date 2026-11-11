"""Решение, на каком языке писать — человеку или работодателю — и искать работу.

Решается здесь и только здесь. Промпты и модули, пишущие человеку или
работодателю, язык не выбирают — им приходит готовая строка: так правило одно,
а не по копии в каждом наставлении, и модель не угадывает его по анкете и посту
каждый раз по-своему. Выбором не считается правило «не переводи»: разбор резюме
пишет поля на языке самого резюме.
"""

from collections.abc import Iterable
from dataclasses import dataclass

from backend.domain.taxonomy import CEFR_LEVELS, LEVEL_REQUIRED_WHEN_UNTOLD, NATIVE_LEVEL

FALLBACK_LANGUAGE = "English"
"""Язык человека, у которого в анкете нет родного."""

INTERNATIONAL_LANGUAGE = "English"
"""Язык готового письма к отклику не на языке приложения.

Значение то же, что у `FALLBACK_LANGUAGE`, но правило другое: язык человека
без родного и язык второй пары писем меняются порознь, и одна константа на оба
незаметно меняла бы второе вместе с первым."""


@dataclass(frozen=True)
class _AppLanguage:
    """Язык, на котором может работать приложение.

    `starts` и `codes` — как его называют: язык поста назван на нём самом, а
    язык анкеты человек вписывает своими словами — «Русский», «русский язык»,
    «Russian», «RU».
    """

    name: str
    starts: tuple[str, ...]
    codes: tuple[str, ...]


_APP_LANGUAGES = {"ru": _AppLanguage("Русский", ("русск", "russ"), ("ru", "rus"))}

APP_LOCALE = "ru"
"""Язык приложения кодом — единственное место, где он задан: бэкенд берёт его
отсюда, окно получает через мост. Выбора пока нет. Кода без записи в
`_APP_LANGUAGES` приложение не примет и не запустится."""

APP_LANGUAGE = _APP_LANGUAGES[APP_LOCALE].name
"""Язык приложения названием — так его видят промпты и выбор готового письма."""


@dataclass(frozen=True)
class CandidateLanguage:
    """Один язык кандидата с CEFR-уровнем (или 'native')."""

    name: str
    level: str  # "A1" | "A2" | "B1" | "B2" | "C1" | "C2" | "native"


def candidate_languages(rows: Iterable) -> list[CandidateLanguage]:
    """Языки анкеты из её строк — чего угодно с `language` и `level`."""
    return [CandidateLanguage(name=row.language, level=row.level) for row in rows]


def person_language(languages: Iterable[CandidateLanguage]) -> str:
    """Язык человека: первый родной в его списке, без родного — английский.

    На нём пишется всё, что приложение говорит самому человеку.
    """
    return next((lang.name for lang in languages if lang.level == NATIVE_LEVEL), FALLBACK_LANGUAGE)


def search_languages(languages: Iterable[CandidateLanguage]) -> list[str]:
    """Языки, на которых искать работу: родные и те, где уровень не ниже
    требуемого без уровня (`LEVEL_REQUIRED_WHEN_UNTOLD`); таких нет — язык
    человека."""
    languages = list(languages)
    usable = (NATIVE_LEVEL, *CEFR_LEVELS[CEFR_LEVELS.index(LEVEL_REQUIRED_WHEN_UNTOLD):])
    return [lang.name for lang in languages if lang.level in usable] or [person_language(languages)]


def in_app_language(language: str) -> bool:
    """На языке ли приложения `language` — названный любым из его имён."""
    app = _APP_LANGUAGES[APP_LOCALE]
    name = language.strip().casefold()
    return name in app.codes or name.startswith(app.starts)


def letter_language(language: str) -> str:
    """Язык готового письма к отклику на `language`: язык приложения, если отклик
    на нём, иначе международный. Готовых писем две пары — на языке приложения и
    международная."""
    return APP_LANGUAGE if in_app_language(language) else INTERNATIONAL_LANGUAGE


def reply_language(vacancy_language: str | None, person: str) -> str:
    """Язык отклика: язык вакансии, а неизвестен он — язык человека.

    Откликом считается всё, что уходит работодателю или вводится в его форму в
    ответ на вакансию: письмо, письмо вдогон, ответы на вопросы формы.
    """
    return vacancy_language or person
