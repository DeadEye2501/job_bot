"""Приведение названий технологий к виду, пригодному для стека вакансии."""


import logging
import re

from backend.domain.skill_names import skill_key
from backend.domain.spellings import dedupe_first_wins
from backend.domain.alphabet import CYRILLIC_LETTER, CYRILLIC_WORD, LATIN_LETTER
from backend.llm.rules import REQUIREMENT_WRAPPERS

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


# Обёртка требования: слова, которыми требование введено, и предлог за ними
# — «опыт работы с Docker», «знание CI/CD», «работа с кассой». Перечень слов
# общий с наставлением (`llm/rules`): порознь они разъезжаются молча.
#
# Перед самой обёрткой допускаются два слова — «уверенный опыт работы с X»,
# «глубокое понимание Y»: перечислить их нельзя, а без них обёртка не
# опознаётся вовсе.
_WRAPPER_HEAD = (
    r"^\s*(?:[а-яё]+\s+){0,2}(?:"
    + "|".join(REQUIREMENT_WRAPPERS)
    + r"|работа|работы)\b"
)
# Хвост требования после обёртки. Между обёрткой и предлогом стоит что угодно
# — «опыт успешной работы с Docker», — поэтому берётся всё после ПОСЛЕДНЕГО
# предлога. Без предлога хвостом считается всё, что идёт за самой обёрткой:
# «знание CI/CD».
_WRAPPED_BY_PREPOSITION_RE = re.compile(
    _WRAPPER_HEAD + r".*?\s(?:с|со|в|во|на|по)\s+(?P<tail>\S.*)$", re.IGNORECASE
)
# Хвост после обёртки без предлога: «знание CI/CD», «владение Photoshop».
_WRAPPED_BARE_RE = re.compile(
    _WRAPPER_HEAD + r"\s+(?P<tail>\S.*)$", re.IGNORECASE
)
# Сколько слов бывает у требования, которое стоит выбросить целиком. Считается
# длина ХВОСТА, а не всей строки: у «опыта успешной работы с кассой» хвост в
# одно слово, и выбрасывать её значило бы терять названный навык. Порог
# работает только вместе с обёрткой — названия без неё по длине не отсеиваются
# вовсе: у строителя и маркетолога они бывают и в шесть слов, «Монтаж систем
# вентиляции и кондиционирования».
_MAX_WRAPPED_WORDS = 4
# Чем разделено перечисление внутри одного требования: запятая, союз «и»,
# английское «and». Косая не разделитель: «CI/CD» — одно имя.
_LISTED_RE = re.compile(r"\s*,\s*|\s+(?:и|and)\s+", re.IGNORECASE)


def _wrapped_tail(s: str) -> str | None:
    """Что стоит за обёрткой требования; пусто — обёртки нет."""
    said = _WRAPPED_BY_PREPOSITION_RE.match(s) or _WRAPPED_BARE_RE.match(s)
    return said.group("tail").strip() if said else None


def _is_name(one: str) -> bool:
    """Написано ли имя латиницей: «.NET», «H&M», «Premiere Pro», «Škoda».

    Обёртка снимается только перед таким: у русского хвоста остаётся падеж
    («ведения соцсетей»), и срезкой слова его не починить — там нужна
    начальная форма, которой у кода нет.
    """
    return bool(LATIN_LETTER.search(one)) and not CYRILLIC_LETTER.search(one)


def _named_tools(s: str) -> list[str]:
    """Имена собственные, названные в требовании; пусто — таких в нём нет.

    Имён бывает несколько: «опыт работы в Excel и Word» называет два, и
    выбросить строку целиком значило бы потерять оба. Перечисление делится
    по запятой и союзу, а косая внутри имени остаётся — «CI/CD» одно имя, а
    не два.
    """
    tail = _wrapped_tail(s)
    if tail is None:
        return []
    found: list[str] = []
    for listed in _LISTED_RE.split(tail):
        for part in CYRILLIC_WORD.split(listed):
            # Точка и амперсанд не срезаются: они часть имени — «.NET», «H&M».
            one = part.strip(" \t,;:()«»\"'-–—")
            if one and _is_name(one):
                found.append(one)
    return found


def _is_wrapped_requirement(s: str) -> bool:
    """Требование ли это целиком — обёртка впереди, а за ней не название.

    Длина считается по тому, что стоит за словом-обёрткой, а не по всей
    строке: у «опыта успешной работы с кассой» за обёрткой четыре слова, и
    это ещё навык, названный длинно, а не переписанное требование.
    """
    said = _WRAPPED_BARE_RE.match(s)
    return said is not None and len(said.group("tail").split()) > _MAX_WRAPPED_WORDS


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
        named = _named_tools(one)
        if named:
            kept.extend(named)
        elif not _is_wrapped_requirement(one):
            kept.append(one)
    return dedupe_first_wins(
        [_capitalize_skill(_strip_version(one)) for one in kept],
        skill_key,
        seen,
    )
