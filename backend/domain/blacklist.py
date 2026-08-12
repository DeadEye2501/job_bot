"""Поиск запрещённого слова в тексте по границам слова."""

import functools
import re


# Используем Python-овский Unicode \w (включает кириллицу, греческий
# и т.п.). Раньше _WORD_CHARS были только ASCII — blacklist-паттерн
# «.NET» матчился внутри «.NETKaфедра», а паттерн «нода» — внутри
# «нодаль» только если соседние буквы были латиницей. Теперь boundary
# работает одинаково для любых алфавитов.
def _is_word_char(ch: str) -> bool:
    """True если символ — Unicode word-char (буква/цифра/_)."""
    return bool(re.match(r"\w", ch, re.UNICODE))


@functools.lru_cache(maxsize=512)
def _compile_word_pattern(variant: str) -> re.Pattern[str]:
    first = variant[0]
    last = variant[-1]
    first_class = (
        r"\w" if _is_word_char(first) else f"[{re.escape(first)}]"
    )
    last_class = (
        r"\w" if _is_word_char(last) else f"[{re.escape(last)}]"
    )
    return re.compile(
        rf"(?<!{first_class}){re.escape(variant)}(?!{last_class})",
        re.UNICODE,
    )


def _word_match(text_lower: str, variant: str) -> bool:
    if not variant:
        return False
    return _compile_word_pattern(variant).search(text_lower) is not None


def check_blacklist(raw_text: str, patterns: list[str]) -> str | None:
    """Первый образец из списка, нашедшийся в тексте по границам слова.

    Ни пустой текст, ни пустой образец отдельного отсева здесь не имеют:
    по пустому тексту поиск и так не находит ничего, а пустой образец
    отсекает `_word_match` — он же и обязан, потому что дальше читает
    первый символ. Отсев поверх этих двух был бы вторым объявлением того
    же знания, и разъехаться они могли бы молча.

    А вот пустотой ни текст, ни образец быть не могут: обоим тут же
    опускают регистр. Зовущие это и держат — текст проверен на непустоту
    выше по стеку, образцы приходят колонкой базы.
    """
    text_lower = raw_text.lower()
    for pattern in patterns:
        if _word_match(text_lower, pattern.lower()):
            return pattern
    return None
