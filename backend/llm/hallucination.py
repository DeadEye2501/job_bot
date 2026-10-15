"""Чем негодно обоснование, которое дала модель.

Негодность бывает двух родов, и следствия у них разные: выдуманный факт
переворачивает вердикт — отказ вынесен по тому, чего в объявлении нет;
сказанное не в той форме гасит одно обоснование, а отказ остаётся. Обе
приметы только называют беду; что с ней делать, решает зовущий.
"""


import re

from backend.domain.taxonomy import CEFR_LEVELS, GRADES
from backend.incoming import fold_signs
from backend.llm.candidate import CandidateProfile

# Уровни языка и грейды приметам нужны перечислением через «или». Собираются
# из общего справочника, а не выписываются руками: вписанные в четырёх местах,
# они разъезжались бы с ним по одному — и примета молча переставала бы ловить
# то, ради чего заведена.
_CEFR_ALT = "|".join(CEFR_LEVELS)
_GRADE_ALT = "|".join(GRADES)

# Универсальные (профиль-независимые) маркеры галлюцинаций. Если LLM в reason
# использовал один из этих маркеров, а в тексте поста его нет — reason не
# подкреплён текстом. Списки специально консервативны: лучше пропустить
# подозрительный случай как fit (пользователь отфильтрует руками), чем
# глушить реальные reject'ы.
# Любой CEFR-уровень или его текстовый эквивалент. Один и тот же regex
# используется и для reason, и для text — если в reason есть упоминание
# уровня, а в посте нет ни одного — это галлюцинация.
#
# Со словарём написаний уровня из `domain/taxonomy` этот перечень намеренно НЕ
# сводится, хотя и похож. Там слова переводят в шкалу, читая резюме, где
# «свободно» стоит рядом с языком; здесь ищут упоминание уровня в объявлении,
# где «свободный график» и «продвинутый пользователь» — не про язык вовсе.
# Общий словарь ловил бы их и объявлял выдумкой честный отказ.
_CEFR_LEVEL_RE = re.compile(
    r"\b(" + "|".join(level.lower() for level in CEFR_LEVELS) + r"|"
    r"upper[\s-]?intermediate|"
    r"intermediate|pre[\s-]?intermediate|elementary|beginner|"
    r"advanced|fluent)\b",
    re.IGNORECASE,
)


_GENERIC_HALLUCINATION_MARKERS: tuple[tuple[re.Pattern[str], re.Pattern[str]], ...] = (
    # Уровень языка сюда не входит: он спрашивается всегда, и с цитатами тоже
    # (см. `looks_hallucinated`).
    # «ежедневные митинги/созвоны/standups» / «daily standup/meeting/sync»
    (
        re.compile(
            r"ежедневн\w*\s+(митинг|созвон|standup|стендап)", re.IGNORECASE
        ),
        re.compile(
            r"(ежедневн\w*\s+(митинг|созвон|standup|стендап)|"
            r"daily\s+(standup|meeting|sync))",
            re.IGNORECASE,
        ),
    ),
)


# Стилевые reason-only паттерны — сработали в reason → fail независимо от
# raw_text. Ловят нарушения стиля «формулируй требование вакансии, не
# пересказывай данные кандидата». Намеренно консервативны: триггерят только
# на формы «<данные кандидата>», где явно сравниваются данные кандидата с
# требованием вакансии (CEFR/грейд/формат). Без такого якоря не триггерим,
# чтобы не ронять легитимные reject'ы по FREE_PREFERENCES, в которых LLM
# естественно скопирует формулировку «не готов / не рассматриваю» из
# {FREE_PREFERENCES}.
_REASON_STYLE_VIOLATIONS: tuple[re.Pattern[str], ...] = (
    # «у кандидата только B1», «у кандидата лишь middle» и т.п. — явное
    # перетягивание данных кандидата в reason
    re.compile(
        r"\bу\s+кандидат\w*\s+(только|лишь|всего|нет)\s+"
        rf"({_CEFR_ALT}|{_GRADE_ALT}|"
        r"office|remote|hybrid|удал[её]нк\w*|оф[ф]?ис\w*|гибрид\w*)",
        re.IGNORECASE,
    ),
    # «кандидат живёт в …», «кандидат находится в …» — пересказ локации
    re.compile(r"\bкандидат\s+живёт\b", re.IGNORECASE),
    re.compile(r"\bкандидат\s+находится\s+в\b", re.IGNORECASE),
    # Парафразы без явного «у кандидата»: «только B1 — недостаточно»,
    # «всего B1 мало», «B1 недостаточно для…». Anchor на CEFR + слова
    # «недостаточно/мало/слабо», чтобы не словить легитимный reject
    # вакансии «требуется C1, а у нас только B2 в требованиях».
    # Расстояние между «только B1» и «недостаточно» bound'нуто 30 char'ами:
    # без bound'а паттерн ловит ложные срабатывания на сложных
    # предложениях с двумя клозами — «у кандидата опыт достаточный, но
    # B1 недостаточно для C1» через всю фразу.
    re.compile(
        rf"\b(только|лишь|всего)\s+({_CEFR_ALT})\b"
        r"[^.]{0,30}\b(недостаточно|мало|слаб)",
        re.IGNORECASE,
    ),
    # Bare «B1 недостаточно» без квантификатора — агрессивно: вакансия
    # сама может цитировать «B1 недостаточно для C1-роли». Триггерим
    # ТОЛЬКО когда рядом «у кандидата»/«его»/«мой», и тоже с bounded gap.
    re.compile(
        r"\b(у\s+кандидат\w*|его|мой)\b[^.]{0,40}"
        rf"\b({_CEFR_ALT})\s+недостаточно\b",
        re.IGNORECASE,
    ),

    # То же по-английски: обоснование пишется на языке человека, и без этих
    # образцов заслон на англоязычном отказе молча выключался бы целиком.
    # «candidate has only B1», «candidate only has middle», «candidate has just A2»
    re.compile(
        r"\bcandidate\s+(only\s+has|has\s+only|has\s+just|only\s+speaks|"
        r"speaks\s+only)\s+"
        rf"({_CEFR_ALT}|{_GRADE_ALT}|office|remote|hybrid)",
        re.IGNORECASE,
    ),
    # «candidate doesn't have / does not have / has no / lacks <X>»
    re.compile(
        r"\bcandidate\s+(doesn'?t\s+have|does\s+not\s+have|has\s+no|lacks)\b",
        re.IGNORECASE,
    ),
    # «candidate's level is only / candidate's <X> is only»
    re.compile(
        r"\bcandidate'?s\s+\w+\s+(is|are)\s+(only|just)\b",
        re.IGNORECASE,
    ),
    # «candidate lives in …», «candidate is located in …», «candidate is based in …»
    re.compile(r"\bcandidate\s+lives\s+in\b", re.IGNORECASE),
    re.compile(r"\bcandidate\s+is\s+(located|based)\s+in\b", re.IGNORECASE),
)


# Канонические корни для ходовых имён языков. Используются вместо «обрежем
# последние 2 символа», чтобы покрыть склоняемые формы («английский»,
# «английского», «английским») одним коротким стволом без коллизий с
# короткими словами вроде «Hi» (приветствие) или «Hin» (короткие префиксы).
#
# ВНИМАНИЕ: это закрытый набор (≈25 ходовых языков). Для языков ВНЕ списка
# используется грубая эвристика name[:-2] (см. language_root ниже). Эвристика срабатывает корректно для большинства склоняемых имён, но
# для коротких/иноалфавитных имён (например, «中文», «हिन्दी», «한국어»)
# safety-net по галлюцинациям этого языка работает грубее. Универсальные
# детекторы (CEFR-маркеры в _GENERIC_HALLUCINATION_MARKERS) работают всегда.
_LANGUAGE_ROOT_OVERRIDES: dict[str, str] = {
    "русский": "русск",
    "английский": "англ",
    "немецкий": "немецк",
    "французский": "французск",
    "испанский": "испанск",
    "итальянский": "итальянск",
    "португальский": "португальск",
    "армянский": "армянск",
    "грузинский": "грузинск",
    "украинский": "украинск",
    "белорусский": "белорусск",
    "польский": "польск",
    "турецкий": "турецк",
    "арабский": "арабск",
    "китайский": "китайск",
    "японский": "японск",
    "корейский": "корейск",
    "хинди": "хинди",
    "english": "engli",
    "russian": "russi",
    "german": "germa",
    "french": "frenc",
    "spanish": "spani",
}


_MIN_LANG_ROOT_LEN = 4


def language_root(name: str) -> str | None:
    """Корень названия языка для поиска по тексту; пусто — маркера не будет.

    Длинное имя теряет хвост склонения, короткое берётся как есть, а
    известные исключения перечислены отдельно. Слишком короткий корень
    маркера не даёт вовсе: он ловился бы в случайных приставках, и отказ
    объявлялся бы выдуманным на ровном месте.
    """
    if not name:
        return None
    key = name.lower()
    if key in _LANGUAGE_ROOT_OVERRIDES:
        root = _LANGUAGE_ROOT_OVERRIDES[key]
    elif len(name) > 6:
        root = name[:-2]
    else:
        root = name
    return root if len(root) >= _MIN_LANG_ROOT_LEN else None


def _language_marker(
    root: str, name: str, inference_verbs: str, cefr_text: str
) -> tuple[re.Pattern[str], re.Pattern[str]]:
    """Пара образцов для одного языка: что искать в обосновании и в тексте.

    В обосновании — вывод «подразумевает <язык>», «требуется <язык>». В
    тексте — сам язык, любой уровень CEFR или «<lang>-speaking»: нашлось
    хоть что-то из этого — вывод подкреплён, не нашлось — выдуман.
    """
    root_re = re.escape(root)
    return (
        re.compile(
            inference_verbs + r"[а-яё\s,\-—]{0,80}?" + root_re,
            re.IGNORECASE,
        ),
        re.compile(
            r"(" + root_re + r"|" + cefr_text + r"|"
            + re.escape(name) + r"[\s-]?speaking)",
            re.IGNORECASE,
        ),
    )


def _build_profile_hallucination_markers(
    profile: CandidateProfile,
) -> tuple[tuple[re.Pattern[str], re.Pattern[str]], ...]:
    """Параметрические маркеры от профиля кандидата.

    Покрывает inference о владении языком: «подразумевает/требует/нужен
    <язык>» в reason без явного упоминания этого языка/CEFR-уровня в тексте
    поста.

    Возвращает кортеж пар (regex_in_reason, regex_in_text). Логика идентична
    _GENERIC_HALLUCINATION_MARKERS. Какие имена маркера не получают — см.
    :func:`language_root`.
    """
    markers: list[tuple[re.Pattern[str], re.Pattern[str]]] = []
    inference_verbs = (
        r"(подразумева|необходим|требу|предполага|нужен|нужна|требуется)"
    )
    # Уровень CEFR подтверждает требование к языку сам по себе: в посте он
    # стоит только про язык. Корень берём из общей константы, чтобы списки
    # не разъезжались.
    cefr_text = _CEFR_LEVEL_RE.pattern
    for lang in profile.languages:
        name = (lang.name or "").strip()
        root = language_root(name)
        if root is None:
            continue
        markers.append(
            _language_marker(root, name, inference_verbs, cefr_text)
        )
    return tuple(markers)


_QUOTE_RE = re.compile(r"«([^»]+)»")
"""Цитата поста в обосновании — в ёлочках: так её велит приводить наставление."""

_CEFR_CODE_RE = re.compile(r"\b(" + _CEFR_ALT + r")\b", re.IGNORECASE)
"""Уровень шкалы в обосновании. Слова уровня («fluent», «advanced») здесь не
ищутся: обоснование пишется на языке человека, и такое слово — пересказ слов
поста на другом языке, а не уровень, которого в посте нет."""


def _flat(text: str) -> str:
    """Текст для сверки цитаты: без регистра, с пробелами, сведёнными к одному,
    и с одним написанием знаков (`incoming.fold_signs`)."""
    return " ".join(fold_signs(text.casefold()).split())


def _quote_found(quote: str, post: str) -> bool:
    """Есть ли цитата в посте. Пропуск «…» делит её на части, и они ищутся в
    том порядке, в каком стоят; цитата из одних пропусков ничего не цитирует."""
    parts = [part.strip() for part in _flat(quote).split("...") if part.strip()]
    at = 0
    for part in parts:
        at = post.find(part, at)
        if at < 0:
            return False
        at += len(part)
    return bool(parts)


def looks_hallucinated(
    reason: str,
    raw_text: str,
    profile: CandidateProfile,
) -> str | None:
    """Обоснование ссылается на то, чего в объявлении нет; отдаёт примету.

    Первой спрашивается цитата: обоснование пишется на языке человека, а слова
    поста приводит в кавычках как есть. Цитата, которой в посте нет, —
    выдумка. Затем уровень языка: шкала одна на все языки, и уровень шкалы в
    обосновании без уровня в посте выдуман, с цитатами или без. Найденная
    цитата — опора, и словесные приметы ниже уже не спрашиваются: они знают
    только русские обороты, и русское обоснование к посту на другом языке не
    нашло бы в нём своего названия языка.

    Без цитат остаются приметы двух родов: общие, не зависящие от кандидата, и
    построенные по языкам его анкеты.

    Осторожна нарочно: пустая примета значит «не поймали», и вердикт модели
    остаётся как есть.
    """
    if not reason:
        return None
    quotes = _QUOTE_RE.findall(reason)
    post = _flat(raw_text)
    missing = next((q for q in quotes if not _quote_found(q, post)), None)
    if missing is not None:
        return f"цитата «{missing}» не из поста"
    if _CEFR_CODE_RE.search(reason) and not _CEFR_LEVEL_RE.search(raw_text):
        return _CEFR_CODE_RE.pattern
    if quotes:
        return None
    for reason_re, text_re in (*_GENERIC_HALLUCINATION_MARKERS, *_build_profile_hallucination_markers(profile)):
        if reason_re.search(reason) and not text_re.search(raw_text):
            return reason_re.pattern
    return None


def breaks_reason_style(reason: str) -> str | None:
    """Обоснование говорит о кандидате, а не о требовании вакансии.

    Отдельно от выдумки, потому что следствие другое: выдуманное обоснование
    отказа переворачивает вердикт — вакансию отвергли по тому, чего в ней
    нет; сказанное не в той форме гасит одно обоснование, а сам отказ
    остаётся. Переверни мы и его, откликатель отправил бы письмо живому HR
    по вакансии, которую модель отвергла по делу.
    """
    if not reason:
        return None
    for style_re in _REASON_STYLE_VIOLATIONS:
        if style_re.search(reason):
            return style_re.pattern
    return None
