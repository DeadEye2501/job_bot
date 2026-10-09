"""Приведение компании к ключам, по которым её сравнивают.

Имя и хост сайта — то, чем пользуется сведение разобранной компании с уже
заведённой, единственный сегодняшний потребитель. Живут отдельно от него
потому, что не знают ни сессии, ни модели: это чистый разбор строк, и
проверяется он сам по себе.
"""

import re

from backend.domain.company_hosts import is_aggregator_host
from backend.domain.hosts import normalize_host
from backend.incoming import text_or_none


# Минимальная транслитерация русского кириллического алфавита в латиницу
# для дедупа имён вида «МТС» / «MTS». Ё → e (как в большинстве passport
# transliteration — для match'а это надёжнее, чем yo).
_CYR_TO_LAT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def _translit_cyr_to_latin(s: str) -> str:
    return "".join(_CYR_TO_LAT.get(ch, ch) for ch in s.lower())


# Юр.формы, снимаемые с обоих краёв имени до сравнения: «ПАО Сбербанк» →
# «sberbank». Сами по себе они не режут ничего — их берут оба перечня ниже.
# Слова уже в латинице и нижнем регистре: транслитерация идёт раньше.
_LEGAL_FORMS = frozenset({
    "pao", "oao", "zao", "ooo", "jsc", "llc", "ltd", "inc", "corp",
    "gmbh", "plc", "sas",
})

# Двухбуквенные формы снимаются только с той стороны, на которой их пишут.
# Русское «АО» стоит с обеих: «АО Сбер» и «МТС, АО» — обычные написания.
# Европейские `SA`, `AG`, `NV`, `BV` пишут только позади имени, и спереди
# двух букв слишком мало, чтобы принимать их за форму: «НВ Групп» со снятым
# `nv` даёт `grupp` и сходится с компанией «Групп» правилом имени, без
# арбитра, — а склейка компаний необратима.
_HEAD_LEGAL_FORMS = _LEGAL_FORMS | {"ao"}
_TAIL_LEGAL_FORMS = _LEGAL_FORMS | {"ao", "sa", "ag", "nv", "bv"}


_QUOTE_CHARS = set("«»\"'`“”„‚‘’")


def _without_edge_legal_forms(words: list[str]) -> list[str]:
    """Слова имени без юр.форм по краям.

    Только по краям: вырезанная посреди имени форма превращает разные
    компании в одну. «Sber AG Tech» и «Sber Tech» дали бы один ключ, и
    `rule_name` свёл бы их без арбитра.

    Края при этом неодинаковые: у хвоста перечень шире на четыре европейские
    формы, которые впереди имени формой не бывают (см. `_HEAD_LEGAL_FORMS` и
    `_TAIL_LEGAL_FORMS`).
    """
    start, end = 0, len(words)
    while start < end and words[start] in _HEAD_LEGAL_FORMS:
        start += 1
    while end > start and words[end - 1] in _TAIL_LEGAL_FORMS:
        end -= 1
    return words[start:end]


def normalize_company_name(s: str | None) -> str:
    """Нормализованная форма имени для deterministic match: lowercase +
    транслитерация + срезанные по краям юр.формы + сглаженные пробелы.

    Форма, написанная точками, здесь не снимается: точки становятся пробелами,
    и `Philips N.V.` даёт `philips n v`, а не `philips`. Так и оставлено
    нарочно — склеить точки значило бы склеить и инициалы, а `Петров С.А.`
    сошёлся бы тогда с «Петров» правилом имени, без арбитра и необратимо.
    Различить отчество и юр.форму здесь нечем, поэтому такие пары доезжают до
    арбитра: его наставление велит не считать юр.форму доводом (правило 4).
    """
    if not s:
        return ""
    s = "".join(ch for ch in s.strip() if ch not in _QUOTE_CHARS)
    s = _translit_cyr_to_latin(s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(_without_edge_legal_forms(s.split()))


def signal_host(host: str) -> str:
    """Хост, очищенный от «нет сигнала о компании». Для всего, что
    является агрегатором/соцсетью/мессенджером, возвращает пустую
    строку: hard-rule по хостам тогда не вето́рит, а обращается с этим
    как с «website не указан». Альтернатива (вето́рить) ломала бы
    очевидные кейсы вроде `(Acme, acme.com)` vs `(Acme, t.me/Acme)`,
    где парсер сунул в company_website ссылку на канал — на самом деле
    это та же компания, и решение должно приниматься по name-match."""
    if not host or is_aggregator_host(host):
        return ""
    return host


def real_corporate_website(url: str | None) -> str | None:
    """Возвращает очищенный URL ТОЛЬКО если это настоящий корпоративный
    домен. Для aggregator/соцсеть/мессенджер ссылок (t.me/Acme,
    linkedin.com/Acme, hh.ru/employer/...) вернёт None — такие URL'ы
    не должны попадать в `company.website`, иначе UI показал бы юзеру
    ссылку-на-канал как «официальный сайт компании», а будущие парсы
    ничего полезного из этого host'а извлечь не смогут.
    Используется как enrichment-гейт И как фильтр при создании новой
    строки — оба пути иначе персистили бы aggregator-URL'ы."""
    cleaned = text_or_none(url)
    if cleaned is None:
        return None
    if not signal_host(normalize_host(cleaned)):
        return None
    return cleaned


def hosts_compatible(a: str, b: str) -> bool:
    """Hard-rule: разные непустые хосты = разные компании. Если один
    хост пустой (компания без указанного сайта) — не блокируем match."""
    if not a or not b:
        return True
    return a == b
