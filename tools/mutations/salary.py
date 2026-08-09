"""Поломки для разбора строки зарплаты.

Разбор ничего не пересчитывает: он достаёт число, как оно записано, и валюту,
если названа. Ломается тут всё тихо — неверное число не роняет ни запись, ни
отбор, оно просто уводит вакансию из выдачи. Поэтому поломки взяты по местам,
где такое уже случалось: пометка масштаба, разряды, дробная часть, границы
диапазона и опознание валюты.

Файл лёг в дерево с юниксовыми переводами строк — не как остальной бэкенд.
"""

LF = "\n"

MUTATIONS = [
    # _AMOUNT_RE: процент премии снова становится границей зарплаты
    (
        "backend/domain/salary.py",
        r'    r"(?P<num>\d+(?:[  ,.]\d{3})*(?:[.,]\d{1,2})?)(?!\d)(?!\s*%)"',
        r'    r"(?P<num>\d+(?:[  ,.]\d{3})*(?:[.,]\d{1,2})?)(?!\d)"',
    ),
    # _AMOUNT_RE: пометка масштаба снова цепляется за начало соседнего слова
    (
        "backend/domain/salary.py",
        r'    r"(?:\s*(?P<scale>(?:k|к|тыс|m|млн|million)(?![a-zа-яё0-9])))?",',
        r'    r"(?:\s*(?P<scale>(?:k|к|тыс|m|млн|million)))?",',
    ),
    # _AMOUNT_RE: пробел-разделитель разрядов снова разрывает число
    (
        "backend/domain/salary.py",
        r'    r"(?P<num>\d+(?:[  ,.]\d{3})*(?:[.,]\d{1,2})?)(?!\d)(?!\s*%)"',
        r'    r"(?P<num>\d+(?:[,.]\d{3})*(?:[.,]\d{1,2})?)(?!\d)(?!\s*%)"',
    ),
    # _SCALES: пометка тысяч перестаёт раскрываться
    (
        "backend/domain/salary.py",
        '_SCALES = {"k": 1000, "к": 1000, "тыс": 1000,',
        '_SCALES = {"k": 1, "к": 1, "тыс": 1,',
    ),
    # _SCALES: пометка миллионов раскрывается как тысячи
    (
        "backend/domain/salary.py",
        '"m": 10**6, "млн": 10**6, "million": 10**6}',
        '"m": 1000, "млн": 1000, "million": 1000}',
    ),
    # _FRACTION_RE: дробная часть перестаёт опознаваться и число уезжает в тысячи
    (
        "backend/domain/salary.py",
        '_FRACTION_RE = re.compile(r"[.,]\\d{1,2}$")',
        '_FRACTION_RE = re.compile(r"(?!)")',
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
    # parse_salary: границы диапазона схлопываются в нижнюю
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
    # _numbers: ноль снова становится нижней границей
    (
        "backend/domain/salary.py",
        "        if value > 0:" + LF,
        "        if True:" + LF,
    ),
    # _numbers: числа перестают раскладываться по возрастанию
    (
        "backend/domain/salary.py",
        "    return sorted(found)",
        "    return found",
    ),
    # _amount: разделители разрядов остаются в числе
    (
        "backend/domain/salary.py",
        '        value = int(re.sub(r"\\D", "", body))',
        "        value = int(body)",
    ),
    # _currency: из двух названных валют снова выбирается первая
    (
        "backend/domain/salary.py",
        "    return named[0] if len(named) == 1 else None",
        "    return named[0] if named else None",
    ),
]
