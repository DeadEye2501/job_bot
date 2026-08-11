"""Приведение названий технологий к виду, пригодному для стека вакансии."""


import logging
import re

from backend.domain.skill_names import dedupe_by_key

logger = logging.getLogger(__name__)


# Failsafe для случаев, когда LLM не выполнил инструкцию "отбрасывай версии".
# Срезает хвост с цифровым суффиксом: "Python 3.13" → "Python", "Python3.13"
# → "Python", "Java 17" → "Java", "Java17" → "Java", "PostgreSQL 14.5" →
# "PostgreSQL", "Node.js 20" → "Node.js", "Go 1.22+" → "Go", "Kafka v2.5"
# → "Kafka". Разделитель перед версией опционален: пробел, точка, дефис,
# подчёркивание или ничего.
_VERSION_SUFFIX_RE = re.compile(r"[\s.\-_]*[vV]?\d+(?:[.\-_]\d+)*\+?\s*$")

# Имена, у которых цифра на конце — своя, а не версия. Перечислены поимённо
# потому, что формой их от версии не отличить: «Web3» и «Java17» устроены
# одинаково, и любое правило по виду цифры ошибается на одном из них.
# Ошибка в эту сторону дешевле обратной: лишний тег «Web» просто не найдётся
# в анкете, а срезанная цифра у «Python3» ломает сверку и мешает схлопывать
# повторы. Список растёт по мере встреч.
_DIGIT_BELONGS_TO_NAME = frozenset({
    "s3", "c4", "web3", "html5", "css3", "oauth1", "oauth2",
    "ipv4", "ipv6", "sha1", "sha256", "sha512", "md5", "base64",
    "utf-8", "utf8", "es5", "es6", "socks5", "x11", "x86_64", "h2",
})


def _strip_version(s: str) -> str:
    """Strip trailing version suffix from a stack tech name."""
    if s.strip().casefold() in _DIGIT_BELONGS_TO_NAME:
        return s
    cleaned = _VERSION_SUFFIX_RE.sub("", s).strip()
    if not cleaned:
        return s
    # Защита от over-strip'а: если после среза не осталось ни одной буквы,
    # исходник был не «имя + версия», а чем-то вроде «1.0 2.0».
    if not any(ch.isalpha() for ch in cleaned):
        return s
    return cleaned


# Failsafe для капитализации стек-тегов. Логика: если слово полностью
# в нижнем регистре (т.е. в нём нет ни одной заглавной буквы) — поднимаем
# первую букву. Слова с уже зафиксированной формой (CamelCase, ALL-CAPS,
# mixed) НЕ ТРОГАЕМ — это сохраняет канонический вид брендов:
# - "SQLAlchemy", "PostgreSQL", "FastAPI", "ClickHouse" — есть заглавные
# - "Node.js" — заглавная N
# - "iOS", "gRPC" — заглавные есть
# - "C++", "C#", ".NET" — заглавные есть
# Только "pytest", "asyncio", "aiohttp", "scapy", "scrapli" и подобные
# all-lowercase теги превращаются в "Pytest", "Asyncio", "Aiohttp" и т.п.
# Многословные значения вроде "микросервисная архитектура" получают
# заглавную для каждого слова, удовлетворяя правилу UI.
def _capitalize_skill(s: str) -> str:
    """Capitalize first letter of each whitespace-separated word in a stack
    tech name, but only for words that are entirely lowercase. Words with
    any uppercase letter are preserved verbatim to keep brand-specific
    casing (SQLAlchemy, PostgreSQL, FastAPI, iOS, Node.js, gRPC) intact."""
    words = s.split(" ")
    out: list[str] = []
    for w in words:
        if not w:
            out.append(w)
            continue
        # Any uppercase letter present → leave as is (brand casing preserved).
        if any(ch.isupper() for ch in w):
            out.append(w)
            continue
        # All-lowercase word → capitalize first cased character.
        # str.capitalize() lowercases the rest, that's fine here because we
        # only enter this branch when the word is already fully lowercase.
        out.append(w[0].upper() + w[1:])
    return " ".join(out)


def clean_stack_items(
    raw: object, seen: set[str]
) -> list[str]:
    """Apply ``_strip_version`` + ``_capitalize_skill`` and de-duplicate
    a single stack-list value from the LLM response.

    ``seen`` is shared between consecutive calls so deduplication spans
    BOTH stack groups (required + preferred) — the prompt forbids the
    same skill from appearing in both, but if the LLM slips up, we
    silently keep only the first occurrence. Order: required is processed
    first (so a duplicate is dropped from preferred).

    Accepts ``list``, ``str`` (split by comma — legacy single-line format),
    or anything else (treated as empty).
    """
    if isinstance(raw, str):
        # LLM нарушил schema-контракт и вернул строку вместо list — попытка
        # восстановления через split(',') как legacy-fallback. Логируем,
        # потому что это сигнал что промпт надо подтянуть либо модель
        # деградировала.
        logger.debug(
            "stack item is a string, falling back to comma-split: %r", raw
        )
        items: list = raw.split(",")
    elif isinstance(raw, list):
        items = raw
    else:
        return []
    # Дедупликация — на случай если LLM вернул "Python 3.13" и "Python"
    # одновременно (после срезки версии оба → "Python"), либо положил один и
    # тот же навык в required и в preferred. Ключ тот же, что у анкеты: иначе
    # «CI/CD» и «ci cd» пережили бы дедупликацию и дали двойной балл за один
    # навык.
    return dedupe_by_key(
        [
            _capitalize_skill(_strip_version(s.strip()))
            for s in items
            if isinstance(s, str)
        ],
        seen,
    )
