"""Приведение свободной строки зарплаты к тысячам рублей."""

import logging
import re

logger = logging.getLogger(__name__)

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
    *,
    usd_rate: int | None = None,
    eur_rate: int | None = None,
) -> tuple[int | None, int | None]:
    """Parse a free-form salary string into (min, max) in thousands of RUB.

    The parser is intentionally lossy — it only needs to be good enough to
    drive the range filter in the vacancy list. Currency rates можно
    передать (per RuntimeSettings.salary_usd_to_rub / _eur_to_rub); если
    не переданы — используются дефолты модуля (90 / 100).

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

    usd_rate = usd_rate if usd_rate and usd_rate > 0 else _SALARY_USD_TO_RUB
    eur_rate = eur_rate if eur_rate and eur_rate > 0 else _SALARY_EUR_TO_RUB
    if _SALARY_USD_RE.search(s):
        currency_mult = usd_rate
    elif _SALARY_EUR_RE.search(s):
        currency_mult = eur_rate
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
