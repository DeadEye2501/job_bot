"""Родной язык кандидата — тот, на котором написано его резюме.

Родной язык у анкеты есть всегда, даже когда раздела языков в резюме нет
вовсе: без него отбор вакансий по языку не знает о человеке ничего.

Называет его модель, а здесь лежит запасной ответ на случай, когда она
родного не назвала. Он груб — считает буквы, — и промах у него один и тот же:
латинское резюме не по-английски. Цена промаха мала: язык правится в окне.
"""

import logging
import re
from dataclasses import replace

from backend.domain.taxonomy import NATIVE_LEVEL
from backend.payloads import ParsedCv, ParsedCvLanguage

logger = logging.getLogger(__name__)

_CYRILLIC = re.compile(r"[а-яё]", re.IGNORECASE)
_LATIN = re.compile(r"[a-z]", re.IGNORECASE)


def _resume_language(text: str) -> str:
    """На каком языке написано резюме — по тому, каких букв в нём больше.

    Технологии, названия компаний и ссылки в русском резюме набраны латиницей,
    и на резюме разработчика их четверть. Большинства это не переворачивает,
    а порог тут был бы числом, взятым с потолка.
    """
    if len(_CYRILLIC.findall(text)) >= len(_LATIN.findall(text)):
        return "Русский"
    return "English"


def with_native_language(parsed: ParsedCv, text: str) -> ParsedCv:
    """Разобранное резюме, в языках которого непременно есть родной.

    Назвала модель родной сама — не трогаем: её ответ точнее подсчёта букв.
    Язык резюме уже назван строкой с другим уровнем — этой строке меняется
    уровень, второй такой же не заводится.
    """
    if any(lang.level == NATIVE_LEVEL for lang in parsed.languages):
        return parsed

    native = _resume_language(text)
    logger.info("разбор резюме: родным назначен %s", native)
    key = native.casefold()
    listed = [lang for lang in parsed.languages if lang.language.casefold() == key]
    if listed:
        languages = [
            replace(lang, level=NATIVE_LEVEL) if lang in listed else lang
            for lang in parsed.languages
        ]
    else:
        languages = [ParsedCvLanguage(language=native, level=NATIVE_LEVEL), *parsed.languages]
    return replace(parsed, languages=languages)
