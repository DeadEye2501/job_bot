"""Разбор свободной строки зарплаты: число, как записано, и валюта."""

import re

from backend.models import Currency

# Число вместе со своими разрядами, дробной частью и собственной пометкой
# масштаба. Пометка ищется не по всей строке, а вплотную к числу и только
# целым словом: иначе «k» в «KPI», «к» в «Краснодаре» и «m» в «month»
# умножают зарплату на тысячу или на миллион.
_AMOUNT_RE = re.compile(
    r"(?P<num>\d+(?:[    ,.]\d{3})*(?:[.,]\d{1,2})?)(?!\d)(?!\s*%)"
    r"(?:\s*(?P<scale>(?:тысяч[аи]?|тыс|миллион[а-яё]*|млн|million|k|к|m)"
    r"(?![a-zа-яё0-9])))?",
    re.IGNORECASE,
)
# Числа одной вилки склеены между собой только тире, «до» и пробелами. Дальше
# такой склейки пометка не идёт: в «300к, опыт от 5 лет» пять — это годы.
_RANGE_GLUE_RE = re.compile(r"[\s\-–—]*(?:до)?[\s\-–—]*")
_THOUSAND = ("k", "к", "тыс")
_FRACTION_RE = re.compile(r"[.,]\d{1,2}$")
# Предел колонки: не влезшее в неё уронило бы запись вакансии на коммите, и
# она осталась бы неразобранной навсегда.
_MAX_AMOUNT = 2**63 - 1
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
    for run in _runs(s):
        marker = next((h["scale"] for h in reversed(run) if h["scale"]), None)
        for hit in run:
            value = _amount(hit["num"], hit["scale"] or marker)
            if 0 < value <= _MAX_AMOUNT:
                found.append(value)
    return sorted(found)


def _runs(s: str) -> list[list[re.Match]]:
    """Числа строки, разбитые на вилки.

    Пометку пишут в конце вилки, а относится она ко всей: «150-200 тыс» — это
    сто пятьдесят и двести тысяч. Чтобы раздать её своим и не задеть чужих,
    числа собираются в связки по тому, что стоит между ними.
    """
    runs: list[list[re.Match]] = []
    for hit in _AMOUNT_RE.finditer(s):
        glued = runs and _RANGE_GLUE_RE.fullmatch(s[runs[-1][-1].end() : hit.start()])
        if glued:
            runs[-1].append(hit)
        else:
            runs.append([hit])
    return runs


def _amount(num: str, scale: str | None) -> int:
    """Одно число: разряды склеены, дробная часть учтена, пометка раскрыта.

    Разделитель разрядов и десятичный знак пишут одними и теми же символами,
    и различает их длина хвоста: «3,000» — три тысячи, «3,5» — три с
    половиной.
    """
    fraction = _FRACTION_RE.search(num)
    whole = num[: fraction.start()] if fraction else num
    value: float = int(re.sub(r"\D", "", whole))
    if fraction:
        value += float("0" + fraction.group().replace(",", "."))
    return int(value * _scale(scale))


def _scale(marker: str | None) -> int:
    """Во сколько раз пометка раскрывает число."""
    if not marker:
        return 1
    return 1000 if marker.lower().startswith(_THOUSAND) else 10**6


def _currency(s: str) -> Currency | None:
    """Валюта строки — только если она в ней одна.

    Названы две — диапазон не имеет смысла ни в одной из них, и выбор первой
    попавшейся спрятал бы вакансию от отбора по второй.
    """
    named = [currency for currency, pattern in _CURRENCIES if pattern.search(s)]
    return named[0] if len(named) == 1 else None
