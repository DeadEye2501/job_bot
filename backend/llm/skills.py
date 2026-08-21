"""Приведение названий технологий к виду, пригодному для стека вакансии."""


import logging
import re

from backend.domain.skill_names import skill_key
from backend.domain.spellings import dedupe_first_wins

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
    # Через дефис пишут те же имена, что и слитно: без обеих форм срезание
    # уносило цифру у одного написания и оставляло у другого.
    "sha-1", "sha-256", "sha-512", "oauth-2", "ipv-4", "ipv-6",
    # Платформы, у которых цифра — часть имени, а не версия. Обе раскладки:
    # в объявлениях они встречаются и латиницей, и кириллицей.
    "bitrix24", "битрикс24", "1c", "1с", "office365",
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


# Слово, которым начинают требование: «опыт работы с Docker», «знание
# CI/CD», «работа с кассой». Обёртка — это то, чем требование введено, а не
# то, что оно называет.
_WRAPPER_HEAD = (
    r"^\s*(?:опыт|опыта|знание|знания|умение|умения|навык|навыки|"
    r"понимание|владение|работа|работы)\b"
)
# Хвост требования после обёртки. Между обёрткой и предлогом стоит что угодно
# — «опыт успешной работы с Docker», — поэтому берётся всё после ПОСЛЕДНЕГО
# предлога. Без предлога хвостом считается всё, что идёт за самой обёрткой:
# «знание CI/CD».
_WRAPPED_BY_PREPOSITION_RE = re.compile(
    _WRAPPER_HEAD + r".*\s(?:с|со|в|во|на)\s+(?P<tail>\S.*)$", re.IGNORECASE
)
# Хвост после обёртки без предлога: «знание CI/CD», «владение Photoshop».
_WRAPPED_BARE_RE = re.compile(
    _WRAPPER_HEAD + r"\s+(?P<tail>\S.*)$", re.IGNORECASE
)
# Сколько слов бывает в требовании, которое стоит выбросить целиком. Порог
# работает только вместе с обёрткой: строка, начатая обёрткой и вытянувшаяся
# в пять слов, — это переписанная строка требований, с анкетой она не
# сойдётся никогда. Названия без обёртки не отсеиваются по длине вовсе: у
# строителя и маркетолога они бывают и в шесть слов — «Монтаж систем
# вентиляции и кондиционирования».
_MAX_WRAPPED_WORDS = 4
_CYRILLIC_RE = re.compile(r"[а-яёА-ЯЁ]")
_LATIN_RE = re.compile(r"[A-Za-z]")


def _wrapped_tail(s: str) -> str | None:
    """Что стоит за обёрткой требования; пусто — обёртки нет."""
    said = _WRAPPED_BY_PREPOSITION_RE.match(s) or _WRAPPED_BARE_RE.match(s)
    return said.group("tail").strip() if said else None


def _named_tool(s: str) -> str | None:
    """Имя собственное из требования; пусто — требование названо не именем.

    Обёртка снимается только перед именем, написанным латиницей: «.NET»,
    «H&M», «Premiere Pro». У русского хвоста остаётся падеж («ведения
    соцсетей»), и срезкой слова его не починить — там нужна начальная форма,
    которой у кода нет, и строка остаётся какой пришла.
    """
    tail = _wrapped_tail(s)
    if tail is None or _CYRILLIC_RE.search(tail) or not _LATIN_RE.search(tail):
        return None
    return tail


def _is_wrapped_requirement(s: str) -> bool:
    """Требование ли это целиком — обёртка впереди и длина не как у названия."""
    return _wrapped_tail(s) is not None and len(s.split()) > _MAX_WRAPPED_WORDS


def _as_items(raw: object) -> list:
    """Список технологий из того, что прислала модель.

    Строка вместо списка — нарушенный договор ответа, и она разбирается
    запятыми как встарь; жалоба в журнал остаётся, потому что это признак:
    либо наставление надо подтянуть, либо модель просела. Всё остальное
    считается пустотой.
    """
    if isinstance(raw, str):
        logger.debug(
            "stack item is a string, falling back to comma-split: %r", raw
        )
        return raw.split(",")
    if isinstance(raw, list):
        return raw
    return []


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
    items = _as_items(raw)
    # Дедупликация — на случай если LLM вернул "Python 3.13" и "Python"
    # одновременно (после срезки версии оба → "Python"), либо положил один и
    # тот же навык в required и в preferred. Ключ тот же, что у анкеты: иначе
    # «CI/CD» и «ci cd» пережили бы дедупликацию и дали двойной балл за один
    # навык.
    # Имя ищется раньше отсева по длине: «опыт успешной работы с Docker» — и
    # требование, и название разом, и выбросить его целиком значило бы
    # потерять названный в нём инструмент.
    kept: list[str] = []
    for one in (s.strip() for s in items if isinstance(s, str)):
        named = _named_tool(one)
        if named is not None:
            kept.append(named)
        elif not _is_wrapped_requirement(one):
            kept.append(one)
    return dedupe_first_wins(
        [_capitalize_skill(_strip_version(one)) for one in kept],
        skill_key,
        seen,
    )
