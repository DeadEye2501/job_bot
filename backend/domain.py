import functools
import logging
import re

import numpy as np

from backend.models import ProfileSkill, VacancyStatus
from backend.payloads import ParsedVacancy


logger = logging.getLogger(__name__)


STICKY_STATUSES = frozenset(
    {
        VacancyStatus.DECLINE,
        VacancyStatus.OFFER,
        VacancyStatus.GHOSTING,
        VacancyStatus.SCAM,
        VacancyStatus.NOT_FIT,
        VacancyStatus.IN_PROGRESS,
    }
)


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


def build_skill_lookup(skills: list[ProfileSkill]) -> set[str]:
    """Casefolded lookup-set of profile skill names + aliases.

    Single source of truth for "is this stack item known to the profile?"
    semantics. Used by:
    - ``score_parsed`` (mapping required/preferred items to a profile skill),
    - ``client.bridge._build_matched_set`` (UI green/grey chip highlighting).

    Casefolded — matches the UI's chip-matched comparison so a chip rendered
    as "matched" in the detail pane and the scoring pass agree on what
    counts as a known skill.
    """
    out: set[str] = set()
    for s in skills:
        if s.name:
            out.add(s.name.casefold())
        for alias in (s.aliases or []):
            if isinstance(alias, str) and alias:
                out.add(alias.casefold())
    return out


def _build_skill_level_lookup(
    skills: list[ProfileSkill],
) -> dict[str, int]:
    """Casefolded ``{name|alias: level}`` map. ``level`` for an alias is
    inherited from its parent ``ProfileSkill`` — aliases are just other
    spellings of the same skill and must score the same.

    If the user has two profile skills whose aliases overlap (shouldn't
    happen in seed data, but the schema doesn't forbid it), the LAST one
    wins — same casefold key just gets overwritten. Acceptable: this is
    user-controlled data, and we'd rather not silently aggregate. We do
    log a debug message on collision so the operator can spot a misseeded
    profile when scores look off.
    """
    out: dict[str, int] = {}

    def _put(key: str, level: int, source: str) -> None:
        prev = out.get(key)
        if prev is not None and prev != level:
            logger.debug(
                "profile skill key collision: %r already mapped to "
                "level=%d, overwritten by %s with level=%d",
                key, prev, source, level,
            )
        out[key] = level

    for s in skills:
        if s.name:
            _put(s.name.casefold(), s.level, f"name={s.name!r}")
        for alias in (s.aliases or []):
            if isinstance(alias, str) and alias:
                _put(alias.casefold(), s.level, f"alias={alias!r}")
    return out


def score_parsed(
    parsed: ParsedVacancy, skills: list[ProfileSkill]
) -> int:
    """Score a vacancy based on its required/preferred stack split (LLM
    already canonicalized & deduplicated — see PARSE_VACANCY_PROMPT).

    Formula (per stack item):

    | situation                     | contribution |
    | ----------------------------- | ------------ |
    | required, profile has it      | +level       |
    | required, profile lacks it    | -1           |
    | preferred, profile has it     | +(level - 1) |
    | preferred, profile lacks it   | 0            |

    Notes:
    - "Profile has it" = case-insensitive match on profile skill name OR
      any of its aliases. LLM is instructed to map mentions to canonical
      profile names, so most matches will be on ``name``; alias-fallback
      handles the case where LLM missed the canonicalization step.
    - ``preferred`` with ``level == 1`` → +0 (formula not clamped). This
      is intentional: a desirable basic skill shouldn't bump the score
      above default.
    """
    if not skills:
        return 0
    level_lookup = _build_skill_level_lookup(skills)
    total = 0
    for item in parsed.stack_required:
        if not isinstance(item, str) or not item:
            continue
        level = level_lookup.get(item.casefold())
        if level is None:
            total -= 1
        else:
            total += level
    for item in parsed.stack_preferred:
        if not isinstance(item, str) or not item:
            continue
        level = level_lookup.get(item.casefold())
        if level is None:
            continue
        total += level - 1
    return total


def check_blacklist(raw_text: str, patterns: list[str]) -> str | None:
    if not raw_text:
        return None
    text_lower = raw_text.lower()
    for pattern in patterns:
        if pattern and _word_match(text_lower, pattern.lower()):
            return pattern
    return None


def is_empty_vacancy(parsed: ParsedVacancy | None) -> bool:
    """True если вакансия — очевидная пустышка/мусор и должна уходить в trash
    без обращения к LLM-валидатору.

    Критерии:
    - parsed is None — LLM не извлёк даже title.
    - title есть, но из 5 ключевых полей (description, stack, hr_contact,
      company_name, salary) заполнено МЕНЬШЕ ДВУХ. Раньше требовалось
      чтобы ВСЕ четыре отсутствовали (description+stack+hr_contact+
      company_name) — это съедало валидные короткие посты типа
      «Junior дизайнер | удалёнка | контакт @anna_hr» (есть title +
      hr_contact, остальное пусто → trash). Теперь нужны хотя бы ДВА
      сигнала из пяти.
    """
    if parsed is None:
        return True
    signals = (
        bool(parsed.description),
        bool(parsed.stack),
        bool(parsed.hr_contact),
        bool(parsed.company_name),
        bool(parsed.salary),
    )
    return sum(signals) < 2


def decide_vacancy_status(
    parsed: ParsedVacancy | None,
    score: int,
    blacklist_match: str | None,
    *,
    threshold: int,
) -> tuple[VacancyStatus, str | None]:
    if parsed is None:
        return VacancyStatus.NOT_FIT, "unparseable"
    if blacklist_match:
        return VacancyStatus.NOT_FIT, f"blacklist: {blacklist_match}"
    if score < threshold:
        return VacancyStatus.NOT_FIT, f"score {score} < {threshold}"
    return VacancyStatus.NEW, None


def should_apply_status(
    current: VacancyStatus,
    new: VacancyStatus,
    *,
    force: bool = False,
) -> bool:
    if current == new:
        return False
    # Принудительная отправка отклика (кнопка «Отправить отклик» в UI):
    # пользователь явно решил, что вакансия достойна отклика, даже если
    # авто-классификатор поставил Not Fit. Разрешаем переход New/Not Fit
    # → Applied поверх sticky-гейта. Остальные sticky-статусы (Decline,
    # Offer, Ghosting, Scam, In Progress) не сбрасываем даже при force —
    # они отражают состояние реального диалога/оффера, и затирать их
    # одной отправкой письма опасно.
    if (
        force
        and new == VacancyStatus.APPLIED
        and current in (VacancyStatus.NEW, VacancyStatus.NOT_FIT)
    ):
        return True
    if current in STICKY_STATUSES:
        return False
    if new == VacancyStatus.ANSWERED:
        return current == VacancyStatus.APPLIED
    return True


_SALARY_USD_TO_RUB = 90
_SALARY_EUR_TO_RUB = 100

_SALARY_NUM_RE = re.compile(r"\d[\d\s ]*\d|\d")
_SALARY_USD_RE = re.compile(r"\$|usd|долл")
_SALARY_EUR_RE = re.compile(r"€|eur|евро")
# K, К (cyrillic), к (cyrillic), m / млн etc — both Latin and Cyrillic forms
# show up because parser output is mixed. Treat ' k ' / 'k.' / 'k$' all as
# the thousands suffix.
_SALARY_THOUSANDS_RE = re.compile(r"(?<![a-zа-я])(?:k|к|тыс)", re.IGNORECASE)
_SALARY_MILLIONS_RE = re.compile(r"(?<![a-zа-я])(?:m|млн|million)", re.IGNORECASE)
# «Зарплата обсуждается / по итогам собеса / по договорённости» — тексты,
# где случайные числа («30 days vacation», «5 лет опыта») не являются
# зарплатой. Ловим до того, как _SALARY_NUM_RE их выловит и насуёт в
# salary_rub_min/max бессмысленные значения, ломающие range-фильтр.
_SALARY_NEGOTIABLE_RE = re.compile(r"собесед|договор|обсужд|negotia")


def normalize_salary_to_rub_thousands(
    salary: str | None,
) -> tuple[int | None, int | None]:
    """Parse a free-form salary string into (min, max) in thousands of RUB.

    The parser is intentionally lossy — it only needs to be good enough to
    drive the range filter in the vacancy list. Currency conversion uses
    static rates (USD≈90, EUR≈100); update if the real rate diverges enough
    to bucket vacancies into the wrong filter slot.

    Returns ``(None, None)`` when no number can be extracted (NULL salary,
    "—", "по итогам собеседования", etc.). When only one number is found,
    both bounds are equal.
    """
    if not salary:
        return (None, None)
    s = salary.strip().lower()
    if not s:
        return (None, None)
    if _SALARY_NEGOTIABLE_RE.search(s):
        # «По итогам собеседования + 30 дней отпуска» извлёк бы 30 в
        # min/max — мусорное значение. Лучше None — UI покажет «—»
        # вместо ложного «30 тыс ₽».
        return (None, None)

    if _SALARY_USD_RE.search(s):
        currency_mult = _SALARY_USD_TO_RUB
    elif _SALARY_EUR_RE.search(s):
        currency_mult = _SALARY_EUR_TO_RUB
    else:
        currency_mult = 1

    has_thousands = _SALARY_THOUSANDS_RE.search(s) is not None
    has_millions = _SALARY_MILLIONS_RE.search(s) is not None

    raw_nums: list[int] = []
    for m in _SALARY_NUM_RE.findall(s):
        digits = re.sub(r"\D", "", m)
        if digits:
            raw_nums.append(int(digits))
    if not raw_nums:
        return (None, None)

    if has_millions:
        # "5 млн" / "5M" → 5000 thousand
        normalized = [n * 1000 for n in raw_nums]
    elif has_thousands:
        # "300K" / "300 тыс" → 300 thousand
        normalized = list(raw_nums)
    else:
        # No marker. Bare numbers > 10_000 are almost certainly whole RUB
        # (e.g. "150 000 — 300 000") and get divided. Smaller bare numbers
        # are ambiguous: "1500-3000" could be either kilorubles or whole
        # rubles, but whole rubles is implausibly low — assume kilorubles
        # and leave them. We log unconverted ranges so we can audit real
        # LLM output and tune later.
        normalized = [n // 1000 if n > 10_000 else n for n in raw_nums]
        if any(0 < n <= 10_000 for n in raw_nums):
            logger.debug(
                "normalize_salary: no K/M marker, treating as kilorubles: %r -> %r",
                salary, normalized,
            )

    in_rub_thousands = [int(n * currency_mult) for n in normalized if n > 0]
    if not in_rub_thousands:
        return (None, None)
    in_rub_thousands.sort()
    return (in_rub_thousands[0], in_rub_thousands[-1])


def cosine_top_match(
    query: np.ndarray,
    ids: np.ndarray,
    matrix: np.ndarray,
    threshold: float = 0.92,
) -> int | None:
    assert len(ids) == matrix.shape[0], "ids/matrix length mismatch"
    if matrix.size == 0:
        return None
    q = np.asarray(query, dtype=np.float32)
    qn = float(np.linalg.norm(q))
    if qn == 0:
        return None
    if matrix.shape[1] != q.shape[0]:
        logger.warning(
            "cosine_top_match: dim mismatch — query %d, matrix %d",
            q.shape[0],
            matrix.shape[1],
        )
        return None
    norms = np.linalg.norm(matrix, axis=1)
    mask = norms > 0
    if not mask.any():
        return None
    sims = np.full(len(ids), -1.0, dtype=np.float32)
    sims[mask] = (matrix[mask] @ q) / (norms[mask] * qn)
    best = int(np.argmax(sims))
    if sims[best] >= threshold:
        return int(ids[best])
    return None
