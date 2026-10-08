"""Родной язык кандидата — тот, на котором написано его резюме.

Родной язык у анкеты есть всегда, даже когда раздела языков в резюме нет
вовсе: без него отбор вакансий по языку не знает о человеке ничего.

Называет его модель, а здесь лежит запасной ответ на случай, когда она
родного не назвала. Он груб — считает буквы, — и промах у него один и тот же:
латинское резюме не по-английски. Цена промаха мала: язык правится в окне.
"""

import logging
from dataclasses import replace

from backend.domain.taxonomy import LEVEL_WHEN_UNTOLD, NATIVE_LEVEL
from backend.domain.alphabet import CYRILLIC_LETTER, LATIN_LETTER
from backend.payloads import ParsedCv, ParsedCvLanguage

logger = logging.getLogger(__name__)



def _resume_language(text: str) -> str:
    """На каком языке написано резюме — по тому, каких букв в нём больше.

    Технологии, названия компаний и ссылки в русском резюме набраны латиницей,
    и на резюме разработчика их четверть. Большинства это не переворачивает,
    а порог тут был бы числом, взятым с потолка.
    """
    if len(CYRILLIC_LETTER.findall(text)) >= len(LATIN_LETTER.findall(text)):
        return "Русский"
    return "English"


def with_native_language(parsed: ParsedCv, text: str) -> ParsedCv:
    """Разобранное резюме, где язык его текста непременно назван родным.

    Родной язык, названный человеком прямо, отменяет всякое угадывание: он
    остаётся единственным родным, а язык резюме получает высший уровень. Своё
    слово человека сильнее вывода из языка письма.

    Спрашивается при этом именно язык резюме, а не «есть ли хоть один
    родной»: модель ставит `native` английскому за строку «Английский —
    Advanced», и по такому вопросу русского в анкете не оказалось бы вовсе.

    Язык резюме уже назван строкой — её уровень остаётся как есть, второй
    такой же строки не заводится. Поднимается он до родного только тогда,
    когда родного не назвали вовсе.
    """
    told = any(lang.level == NATIVE_LEVEL for lang in parsed.languages)
    native = _resume_language(text)
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
