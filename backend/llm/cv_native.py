"""Родной язык кандидата, когда резюме его не называет, — язык текста резюме.

Язык текста называет модель: по буквам латиница не отличает испанский от
английского. Язык правится в окне, если и она промахнулась.
"""

import logging
from dataclasses import replace

from backend.domain.taxonomy import LEVEL_WHEN_UNTOLD, NATIVE_LEVEL
from backend.payloads import ParsedCv, ParsedCvLanguage

logger = logging.getLogger(__name__)


def with_native_language(parsed: ParsedCv) -> ParsedCv:
    """Разобранное резюме, где язык его текста назван родным, если резюме
    родного не называет.

    Родной язык, названный резюме прямо, отменяет вывод из языка текста: он
    остаётся единственным родным, а язык текста получает высший уровень. Своё
    слово человека сильнее вывода из языка письма.

    Язык текста уже назван строкой — её уровень остаётся как есть, второй
    такой же строки не заводится. Поднимается он до родного только тогда,
    когда родного не назвали вовсе.
    """
    native = parsed.text_language
    if native is None:
        return parsed
    told = any(lang.level == NATIVE_LEVEL for lang in parsed.languages)
    key = native.casefold()
    listed = [lang for lang in parsed.languages if lang.language.casefold() == key]

    if listed:
        if told:
            return parsed
        return replace(
            parsed,
            languages=[
                replace(lang, level=NATIVE_LEVEL) if lang in listed else lang
                for lang in parsed.languages
            ],
        )

    level = LEVEL_WHEN_UNTOLD if told else NATIVE_LEVEL
    logger.info("разбор резюме: языку резюме %s назначен уровень %s", native, level)
    return replace(
        parsed,
        languages=[
            ParsedCvLanguage(language=native, level=level),
            *parsed.languages,
        ],
    )
