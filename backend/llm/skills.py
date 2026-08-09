"""Приведение названий технологий к виду, пригодному для стека вакансии."""


import logging
import re

logger = logging.getLogger(__name__)


# Failsafe для случаев, когда LLM не выполнил инструкцию "отбрасывай версии".
# Срезает хвост с цифровым суффиксом: "Python 3.13" → "Python", "Python3.13"
# → "Python", "Java 17" → "Java", "Java17" → "Java", "PostgreSQL 14.5" →
# "PostgreSQL", "Node.js 20" → "Node.js", "Go 1.22+" → "Go", "Kafka v2.5"
# → "Kafka". Whitespace перед версией опционален (раньше был обязателен —
# "Python3.13" проскакивал).
# Min-length guard: оставляем только если в результате ≥3 символов с
# буквой. Это спасает "Web3", "S3", "C4" — они идут в стек как есть, без
# срезания цифры на конце ("Web" / "S" / "C" — бессмысленно).
_VERSION_SUFFIX_RE = re.compile(r"\s*v?\d+(?:[.\-_]\d+)*\+?\s*$")


def _strip_version(s: str) -> str:
    """Strip trailing version suffix from a stack tech name."""
    cleaned = _VERSION_SUFFIX_RE.sub("", s).strip()
    if not cleaned:
        return s
    # Защита от over-strip'а: если после среза осталось <3 символов или
    # ни одной буквы — значит исходник был «короткое имя + цифра в составе
    # имени» (Web3, S3, C4), не «версия». Возвращаем оригинал.
    if len(cleaned) < 3 or not any(ch.isalpha() for ch in cleaned):
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
    out: list[str] = []
    for s in items:
        if not isinstance(s, str):
            continue
        cleaned = _capitalize_skill(_strip_version(s.strip()))
        if not cleaned:
            continue
        # case-insensitive дедупликация — на случай если LLM вернул
        # "Python 3.13" и "Python" одновременно (после strip оба → "Python"),
        # либо положил один и тот же скилл в required и в preferred.
        # ``casefold`` вместо ``lower`` для корректной нормализации не-ASCII
        # (ß, İ, …) и согласованности с ``_build_skill_level_lookup``.
        key = cleaned.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(cleaned)
    return out
