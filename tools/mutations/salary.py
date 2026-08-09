"""Поломки для разбора строки зарплаты.

Разбор ничего не пересчитывает: он достаёт число, как оно записано, и валюту,
если названа. Ломается тут всё тихо — неверное число не роняет ни запись, ни
отбор, оно просто уводит вакансию из выдачи или тащит её в чужую. Поэтому
поломки взяты по местам, где разбор уже врал: пометка масштаба, разделители
разрядов, дробная часть, границы вилки и опознание валюты.

Разбираемый файл лёг в дерево с юниксовыми переводами строк — не как остальной
бэкенд; многострочные поломки пишутся через `LF`.
"""

LF = "\n"

MUTATIONS = [
    # _AMOUNT_RE: процент премии снова становится границей зарплаты
    (
        "backend/domain/salary.py",
        r"(?!\d)(?!\s*%)",
        r"(?!\d)",
    ),
    # _AMOUNT_RE: типографский пробел разрядов снова разрывает число
    (
        "backend/domain/salary.py",
        r"[    ,.]\d{3}",
        r"[ ,.]\d{3}",
    ),
    # _AMOUNT_RE: обычный пробел разрядов снова разрывает число
    (
        "backend/domain/salary.py",
        r"[    ,.]\d{3}",
        r"[   ,.]\d{3}",
    ),
    # _AMOUNT_RE: пометка масштаба снова цепляется за начало соседнего слова
    (
        "backend/domain/salary.py",
        r'    r"(?![a-zа-яё0-9])))?",',
        r'    r")))?",',
    ),
    # _AMOUNT_RE: пометка, написанная словом целиком, перестаёт опознаваться
    (
        "backend/domain/salary.py",
        "тысяч[аи]?|тыс|миллион[а-яё]*|млн",
        "тыс|млн",
    ),
    # _scale: пометка тысяч перестаёт раскрываться
    (
        "backend/domain/salary.py",
        "    return 1000 if marker.lower().startswith(_THOUSAND) else 10**6",
        "    return 1 if marker.lower().startswith(_THOUSAND) else 10**6",
    ),
    # _scale: пометка миллионов раскрывается как тысячи
    (
        "backend/domain/salary.py",
        "    return 1000 if marker.lower().startswith(_THOUSAND) else 10**6",
        "    return 1000 if marker.lower().startswith(_THOUSAND) else 1000",
    ),
    # _amount: дробная часть перестаёт отделяться от разрядов
    (
        "backend/domain/salary.py",
        '_FRACTION_RE = re.compile(r"[.,]\\d{1,2}$")',
        '_FRACTION_RE = re.compile(r"(?!)")',
    ),
    # _amount: разделители разрядов остаются в числе
    (
        "backend/domain/salary.py",
        '    value: float = int(re.sub(r"\\D", "", whole))',
        "    value: float = int(whole)",
    ),
    # _runs: пометка вилки достаётся только своему числу
    (
        "backend/domain/salary.py",
        '        marker = next((h["scale"] for h in reversed(run) if h["scale"]), None)' + LF,
        "        marker = None" + LF,
    ),
    # _runs: пометка выходит за свою вилку и умножает чужие числа
    (
        "backend/domain/salary.py",
        '        glued = runs and _RANGE_GLUE_RE.fullmatch(s[runs[-1][-1].end() : hit.start()])',
        "        glued = bool(runs)",
    ),
    # _numbers: ноль снова становится нижней границей
    (
        "backend/domain/salary.py",
        "            if 0 < value <= _MAX_AMOUNT:" + LF,
        "            if value <= _MAX_AMOUNT:" + LF,
    ),
    # _numbers: число, не влезающее в колонку, снова доходит до записи
    (
        "backend/domain/salary.py",
        "            if 0 < value <= _MAX_AMOUNT:" + LF,
        "            if 0 < value:" + LF,
    ),
    # _numbers: числа перестают раскладываться по возрастанию
    (
        "backend/domain/salary.py",
        "    return sorted(found)",
        "    return found",
    ),
    # _NEGOTIABLE_RE: «договорная» снова перестаёт отменять зарплату
    (
        "backend/domain/salary.py",
        "|договорённ|договоренн|договорн|",
        "|",
    ),
    # _CURRENCIES: «евро» снова опознаётся внутри «Европы»
    (
        "backend/domain/salary.py",
        "|евро(?![а-яё])",
        "|евро",
    ),
    # parse_salary: границы вилки схлопываются в нижнюю
    (
        "backend/domain/salary.py",
        "    return (numbers[0], numbers[-1], _currency(s))",
        "    return (numbers[0], numbers[0], _currency(s))",
    ),
    # parse_salary: регистр строки перестаёт опускаться
    (
        "backend/domain/salary.py",
        "    s = salary.strip().lower()",
        "    s = salary.strip()",
    ),
    # _currency: из двух названных валют снова выбирается первая
    (
        "backend/domain/salary.py",
        "    return named[0] if len(named) == 1 else None",
        "    return named[0] if named else None",
    ),
]
