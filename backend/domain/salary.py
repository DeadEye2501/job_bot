"""Разбор свободной строки зарплаты: число, как записано, и валюта."""

import re

from backend.models import Currency

# Число вместе со своими разрядами, дробной частью и собственной пометкой
# масштаба. Пометка ищется не по всей строке, а вплотную к числу и только
# целым словом: иначе «k» в «KPI», «к» в «Краснодаре» и «m» в «month»
# умножают зарплату на тысячу или на миллион.
_AMOUNT_RE = re.compile(
    r"(?P<num>\d+(?:[  ,.]\d{3})*(?:[.,]\d{1,2})?)(?!\d)(?!\s*%)"
    r"(?:\s*(?P<scale>(?:k|к|тыс|m|млн|million)(?![a-zа-яё0-9])))?",
    re.IGNORECASE,
)
_SCALES = {"k": 1000, "к": 1000, "тыс": 1000, "m": 10**6, "млн": 10**6, "million": 10**6}
_FRACTION_RE = re.compile(r"[.,]\d{1,2}$")
# «Зарплата обсуждается / по договорённости» — тексты, где случайные числа
# («30 дней отпуска», «5 лет опыта») зарплатой не являются. Голое «договор»
# сюда не годится: «трудовой договор» и «договор ГПХ» стоят рядом с прямо
# названной суммой.
_NEGOTIABLE_RE = re.compile(r"собесед|договорённ|договоренн|договорн|обсужд|negotia")
# Название валюты берётся целым словом: «евро» внутри «Европы» и «eur»
# внутри «europe» превращали рублёвую вакансию в валютную.
_CURRENCIES: tuple[tuple[Currency, re.Pattern[str]], ...] = (
    (Currency.USD, re.compile(r"\$|(?<![a-z])usd(?![a-z])|долл")),
    (Currency.EUR, re.compile(r"€|(?<![a-z])eur(?![a-z])|евро(?![а-яё])")),
    (Currency.RUB, re.compile(r"₽|(?<![a-z])rub(?![a-z])|руб")),
)


def parse_salary(
    salary: str | None,
) -> tuple[int | None, int | None, Currency | None]:
    """Достать из строки диапазон и валюту, не пересчитывая их.

    Число остаётся тем, что записано в объявлении, — раскрывается только
    пометка тысяч и миллионов, без которой «300к» не сравнить с «300000».
    Отдаёт ``(None, None, None)``, когда числа в строке нет вовсе или она
    вообще не о деньгах. Одно число даёт равные границы. Валюта, не названная
    в строке, остаётся неизвестной: догадка «раз без знака, то рубли»
    отправила бы долларовую вакансию в рублёвую выдачу.
    """
    if not salary:
        return (None, None, None)
    s = salary.strip().lower()
    if _NEGOTIABLE_RE.search(s):
        return (None, None, None)

    numbers = _numbers(s)
    if not numbers:
        return (None, None, None)
    return (numbers[0], numbers[-1], _currency(s))


def _numbers(s: str) -> list[int]:
    """Числа строки, раскрытые по своей пометке и разложенные по возрастанию.

    Ноль отбрасывается: нулевой зарплаты не бывает, а нижней границей он
    отсёк бы вакансию от любого осмысленного отбора.
    """
    found: list[int] = []
    for hit in _AMOUNT_RE.finditer(s):
        value = _amount(hit.group("num"), hit.group("scale"))
        if value > 0:
            found.append(value)
    return sorted(found)


def _amount(num: str, scale: str | None) -> int:
    """Одно число: разряды склеены, дробная часть учтена, пометка раскрыта.

    Разделитель разрядов и десятичный знак пишут одними и теми же символами,
    и различает их длина хвоста: «3,000» — три тысячи, «3,5» — три с
    половиной.
    """
    body = num.replace(" ", " ")
    if _FRACTION_RE.search(body):
        value = float(body.replace(" ", "").replace(",", "."))
    else:
        value = int(re.sub(r"\D", "", body))
    return int(value * _SCALES.get((scale or "").lower(), 1))


def _currency(s: str) -> Currency | None:
    """Валюта строки — только если она в ней одна.

    Названы две — диапазон не имеет смысла ни в одной из них, и выбор первой
    попавшейся спрятал бы вакансию от отбора по второй.
    """
    named = [currency for currency, pattern in _CURRENCIES if pattern.search(s)]
    return named[0] if len(named) == 1 else None
