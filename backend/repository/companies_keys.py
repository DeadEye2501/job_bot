"""Приведение компании к ключам, по которым её сравнивают.

Имя и хост сайта — то, чем пользуется сведение разобранной компании с уже
заведённой, единственный сегодняшний потребитель. Живут отдельно от него
потому, что не знают ни сессии, ни модели: это чистый разбор строк, и
проверяется он сам по себе.
"""

import re


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


# Юр.формы вырезаются из имени до сравнения: «ПАО Сбербанк» → «sberbank».
# Регистр и кириллица — после lower() и transliterate.
_LEGAL_SUFFIX_RE = re.compile(
    r"\b(pao|oao|ao|zao|ooo|jsc|llc|ltd|inc|corp|gmbh|sa|ag|nv|bv|plc|sas)\b\.?"
)


_QUOTE_CHARS = set("«»\"'`“”„‚‘’")


def normalize_company_name(s: str | None) -> str:
    """Нормализованная форма имени для deterministic match: lowercase +
    транслитерация + срезанные юр.суффиксы + сглаженные пробелы."""
    if not s:
        return ""
    s = "".join(ch for ch in s.strip() if ch not in _QUOTE_CHARS)
    s = _translit_cyr_to_latin(s)
    s = _LEGAL_SUFFIX_RE.sub(" ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def normalize_host(url: str | None) -> str:
    """Хост сайта без схемы / www. / порта / пути / query / fragment /
    завершающей точки. Пустая строка для None или невалидного URL.
    Полный host (а не registrable domain) — чтобы `pay.yandex.ru` ≠
    `yandex.ru` (subsidiary trap)."""
    if not url:
        return ""
    s = url.strip().lower()
    s = re.sub(r"^[a-z][a-z0-9+.\-]*://", "", s)
    s = s.lstrip("/")
    # Срезаем path / query / fragment ДО того, как лезть в port:
    # "sber.ru?utm=foo" без strip-а query превратился бы в host
    # "sber.ru?utm=foo" и сломал бы host-match.
    s = s.split("/", 1)[0]
    s = s.split("?", 1)[0]
    s = s.split("#", 1)[0]
    s = s.split(":", 1)[0]
    if s.startswith("www."):
        s = s[4:]
    # FQDN с завершающей точкой ("example.com.") — нормализуем к
    # "example.com", иначе host-match отказывает на пустяковом расхождении.
    s = s.rstrip(".")
    return s


# Хосты, которые НЕ являются «домашним сайтом компании»: агрегаторы
# вакансий, соцсети, мессенджеры, блог-платформы. Если parser ошибся и
# сунул в `company_website` ссылку на канал/профиль/пост, Stage 1c (host-
# match) мог бы склеить две разные компании по этому общему host'у. Для
# таких host'ов host-match пропускается; останутся только name/alias-match
# и Stage 2 LLM.
_AGGREGATOR_HOSTS = frozenset({
    "t.me",
    "telegram.me",
    "telegram.org",
    "linkedin.com",
    "hh.ru",
    "habr.com",
    "vc.ru",
    "github.com",
    "gitlab.com",
    "avito.ru",
    "superjob.ru",
    "facebook.com",
    "instagram.com",
    "twitter.com",
    "x.com",
    "vk.com",
    "ok.ru",
    "youtube.com",
    "behance.net",
    "dribbble.com",
    "medium.com",
    # Шеринговые хостинги job-страниц / резидент-каталоги: на одном
    # хосте сидит много разных компаний → Stage 1c (website-match) на
    # таком общем домене склеит их в одну. Любой *.potok.io,
    # *.huntflow.io и т.п. — это резюме-/job-board, а не сайт компании.
    "potok.io",
    "huntflow.io",
    "huntflow.ru",
    "amazingjobs.ru",
    "getmatch.ru",
    "jobs.ru",
    "talantix.ru",
    "rabota.ru",
    "trudvsem.ru",
    "career.ru",
})


def _is_aggregator_host(host: str) -> bool:
    """True если host — агрегатор/соцсеть/мессенджер, а не корпоративный
    сайт. Suffix-match: ловит и `linkedin.com`, и `m.linkedin.com`,
    `careers.hh.ru` и т.п."""
    if not host:
        return False
    for h in _AGGREGATOR_HOSTS:
        if host == h or host.endswith("." + h):
            return True
    return False


def signal_host(host: str) -> str:
    """Хост, очищенный от «нет сигнала о компании». Для всего, что
    является агрегатором/соцсетью/мессенджером, возвращает пустую
    строку: hard-rule по хостам тогда не вето́рит, а обращается с этим
    как с «website не указан». Альтернатива (вето́рить) ломала бы
    очевидные кейсы вроде `(Acme, acme.com)` vs `(Acme, t.me/Acme)`,
    где парсер сунул в company_website ссылку на канал — на самом деле
    это та же компания, и решение должно приниматься по name-match."""
    if not host or _is_aggregator_host(host):
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
    cleaned = (url or "").strip() or None
    if not cleaned:
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
