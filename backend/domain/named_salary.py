"""Зарплата для вакансии: отсеять ли её и какую сумму назвать работодателю.

Считает код, а не модель: модель путала минимальную, желаемую и вилку, а
сумма, названная не та, стоит человеку работы или денег. Модель даёт только
период и валюту вилки при разборе; дальше — этот модуль.

Вилка переводится в валюту и период анкеты; сравнивается точный перевод, а
округляется только названная сумма — иначе округление отсеивало бы вакансию,
чей верх на деле не ниже минимальной.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from backend.domain.salary import parse_salary, salary_text
from backend.models import Profile, SalaryPeriod

# Валюта и период анкеты, пока человек их не сменил: анкета без них не бывает.
# Те же значения — `server_default` в `models/profile.py`: модель отсюда их не
# возьмёт, этот модуль сам импортирует `backend.models`.
DEFAULT_CURRENCY = "$"
DEFAULT_PERIOD = SalaryPeriod.MONTH

_PERIOD_WORDS = {SalaryPeriod.HOUR: "в час", SalaryPeriod.MONTH: "в месяц", SalaryPeriod.YEAR: "в год"}

_HOURS_IN_MONTH = 168
_MONTHS_IN_YEAR = 12

Rates = Mapping[str, float]
"""Знак валюты → единиц за 1 USD."""


@dataclass(frozen=True)
class Offer:
    """Вилка вакансии."""

    low: int | None
    high: int | None
    currency: str | None
    period: SalaryPeriod | None


@dataclass(frozen=True)
class SalaryAsk:
    """Зарплата анкеты; пустая — анкеты нет."""

    minimum: int | None = None
    desired: int | None = None
    currency: str = DEFAULT_CURRENCY
    period: SalaryPeriod = DEFAULT_PERIOD


@dataclass(frozen=True)
class Pay:
    """Названная сумма."""

    amount: float
    currency: str
    period: SalaryPeriod


@dataclass(frozen=True)
class SalaryVerdict:
    refusal: str | None
    """Причина отсева; пусто — не отсеяна."""
    pay: Pay | None
    """Что назвать; пусто — назвать нечего. Есть и при отказе: вакансию,
    заведённую вручную, отказ не отсеивает, и откликатель называет верх."""


def offer_period(low: int | None, high: int | None, period: SalaryPeriod | None) -> SalaryPeriod | None:
    """Период вилки: суммы нет — нет и периода (модель называет его и у «по
    договорённости»); сумма есть, а период не назван — месяц, как пишут чаще всего."""
    if low is None and high is None:
        return None
    return period or SalaryPeriod.MONTH


def offer_of(salary: str | None, period: SalaryPeriod | None, currency: str | None) -> Offer:
    """Вилка из строки зарплаты и ответа модели. Валюта, названная в строке,
    сильнее модели: модель выводит валюту из страны и языка, а строка её пишет."""
    low, high, named = parse_salary(salary)
    if low is None and high is None:
        return Offer(None, None, None, None)
    return Offer(low, high, named or currency, offer_period(low, high, period))


def salary_ask_of(profile: Profile | None) -> SalaryAsk:
    if profile is None:
        return SalaryAsk()
    return SalaryAsk(
        minimum=profile.minimum_salary,
        desired=profile.expected_salary,
        currency=profile.expected_salary_currency,
        period=profile.expected_salary_period,
    )


def judge_salary(offer: Offer, ask: SalaryAsk, rates: Rates) -> SalaryVerdict:
    """Отсев и названная сумма по вилке.

    Верх есть — он и решает: ниже минимальной — отсев, иначе он и назван; низ
    при верхе не важен. Только низ — большее из низа и желаемой, без отсева:
    потолок неизвестен. Вилки нет, нет её валюты или периода — желаемая.
    Периода нет у вакансий, разобранных до его появления: месяц по умолчанию
    назвал бы почасовую ставку месячной.
    """
    if offer.currency is None or offer.period is None:
        return SalaryVerdict(None, _desired(ask))
    if offer.high is not None:
        exact = _in_ask_units(offer.high, offer, ask, rates)
        refusal = _refusal(offer) if ask.minimum is not None and exact < ask.minimum else None
        return SalaryVerdict(refusal, _named(offer.high, exact, offer, ask))
    if offer.low is not None:
        exact = _in_ask_units(offer.low, offer, ask, rates)
        if ask.desired is not None and ask.desired >= exact:
            return SalaryVerdict(None, _desired(ask))
        return SalaryVerdict(None, _named(offer.low, exact, offer, ask))
    return SalaryVerdict(None, _desired(ask))


def money_text(amount: float, currency: str, period: SalaryPeriod) -> str:
    """Сумма для анкеты агента. Без «.0» у целого: «200000.0 ₽» читается как опечатка."""
    shown = int(amount) if float(amount).is_integer() else amount
    return f"{salary_text(shown, shown, currency)} {_PERIOD_WORDS[period]}, на руки"


def _desired(ask: SalaryAsk) -> Pay | None:
    return None if ask.desired is None else Pay(ask.desired, ask.currency, ask.period)


def _refusal(offer: Offer) -> str:
    return f"Зарплата ниже минимальной: {salary_text(None, offer.high, offer.currency)} {_PERIOD_WORDS[offer.period]}."


def _named(amount: int, exact: float, offer: Offer, ask: SalaryAsk) -> Pay:
    """Сумма без перевода — как в вакансии; переведённая — круглой, как её
    назвал бы человек."""
    if offer.currency == ask.currency and offer.period == ask.period:
        return Pay(amount, ask.currency, ask.period)
    return Pay(_two_digits(exact), ask.currency, ask.period)


def _in_ask_units(amount: int, offer: Offer, ask: SalaryAsk, rates: Rates) -> float:
    """Сумма вилки в валюте и периоде анкеты, без округления. Курс совпавшей
    валюте не нужен; чужой — есть всегда: кэш курсов заполняет миграция."""
    value = float(amount)
    if offer.currency != ask.currency:
        value = value / rates[offer.currency] * rates[ask.currency]
    return _from_month(_to_month(value, offer.period), ask.period)


def _to_month(value: float, period: SalaryPeriod) -> float:
    if period is SalaryPeriod.HOUR:
        return value * _HOURS_IN_MONTH
    if period is SalaryPeriod.YEAR:
        return value / _MONTHS_IN_YEAR
    return value


def _from_month(value: float, period: SalaryPeriod) -> float:
    if period is SalaryPeriod.HOUR:
        return value / _HOURS_IN_MONTH
    if period is SalaryPeriod.YEAR:
        return value * _MONTHS_IN_YEAR
    return value


def _two_digits(value: float) -> float:
    """Две значащие цифры, половина — вверх: `round` вёл бы половину к чётному,
    и 1250 стало бы 1200."""
    exact = Decimal(str(value))
    step = Decimal(1).scaleb(exact.adjusted() - 1)
    return float(exact.quantize(step, rounding=ROUND_HALF_UP))
