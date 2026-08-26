"""Что в разобранном резюме не подтверждается его же текстом.

Запрет «не выдумывай» стоит в промпте, но держат его не все модели: на четырёх
миллиардах параметров резюме без единого слова о грейде возвращается с
`middle` и `senior`, а резюме без раздела языков — с родным языком, выведенным
из имени кандидата. Слова в промпте это не лечит: пробовали, помогло только
там, где выдумку было чем заменить.

Сверяются грейд, формат работы, язык, уровень языка и стек места работы — по
цене ошибки: по первым четырём отбирают вакансии, а стек связывает работу с
навыками анкеты. Выдуманный `senior` уводит от подходящих объявлений,
выдуманный язык приводит к неподходящим.

Спрашивают по-разному, потому что и врут по-разному. Грейд, язык и уровень
модель придумывает целиком — их ищут в тексте дословно. В стек она кладёт
названия настоящие, но не с той работы, и дословный поиск их находит; поэтому
у стека спрашивают не название, а заголовок над ним. Формат спрашивают списком
целиком: там опасна не потеря значения, а неверный остаток.

Остальное сверять нечем: достижение своими словами пересказано законно и в
тексте дословно не ищется.

Сосед по замыслу — `hallucination.py`: там тем же вопросом проверяют
обоснование вердикта по вакансии. Отличает предмет: там объявление и приговор
о нём, здесь резюме и анкета из него. Разбор названия языка со склонениями у
них общий и живёт у соседа.
"""

import logging
import re
from dataclasses import replace

from backend.domain.taxonomy import (
    CEFR_LEVELS,
    GRADE_SPELLINGS,
    LEVEL_SPELLINGS,
    LEVELS_BY_SPELLING,
    NATIVE_LEVEL,
    WORK_FORMAT_SPELLINGS,
)
from backend.incoming import fold_homoglyphs
from backend.llm.hallucination import language_root
from backend.payloads import ParsedCv

logger = logging.getLogger(__name__)


def _spelled_in(text: str, word: str) -> bool:
    """Слово стоит в тексте само, а не прячется внутри другого.

    Начало стережёт граница слова: без неё «валидация» подтверждала бы «лид».
    Конец — запретом на латинскую букву следом, а не второй границей: русское
    звание в тексте склоняют («сеньора», «тимлида»), и хвост ему нужен, а
    английское, наоборот, обязано кончиться — иначе «middleware» подтвердит
    «middle».
    """
    return re.search(r"\b" + re.escape(word) + r"(?![a-z])", text) is not None


def _any_named_in(text: str, words: tuple[str, ...]) -> bool:
    """Хоть одно из написаний стоит в тексте.

    «Ё» в резюме пишут через раз, и «стажер» — то же слово, что «стажёр». Не
    своди их — и настоящее звание объявлялось бы выдуманным.
    """
    plain = text.replace("ё", "е")
    return any(_spelled_in(plain, word.replace("ё", "е")) for word in words)


def _grounded_formats(text: str, formats: list[str]) -> list[str]:
    """Форматы работы, если КАЖДЫЙ назван в тексте; иначе ни одного.

    Списком целиком, а не по одному значению, и вот почему. Пустой список
    выключает отбор вакансий по формату, непустой — включает и отвергает всё,
    чего в нём нет. Вредна поэтому не потеря значения, а неверный непустой
    список: оставь «гибрид» от пары «гибрид, офис» — и человеку начнут
    отказывать по офисным вакансиям, которых он не отвергал.

    Грейд сверяется иначе, по одному значению, и это не разнобой: звания
    («senior», «тимлид») в резюме ни с чем не путаются, а слова форматов
    сидят внутри «офисного пакета» и «удаления данных», и доверия каждому
    по отдельности меньше.
    """
    named = all(
        _any_named_in(text, WORK_FORMAT_SPELLINGS.get(one, ())) for one in formats
    )
    return list(formats) if named else []


def _language_named_in(text: str, name: str) -> bool:
    """Язык назван в тексте; непроверяемое имя считается названным.

    Корня не бывает у имён в два-три знака — «中文», «한국어». Сосед, у которого
    корень и берётся, считает такое имя причиной проверку пропустить, и здесь
    ответ тот же: сверка заведена против выдумки, а выбросить настоящее — беда
    крупнее той, от которой она сторожит.

    Названный на другом языке, чем в резюме («English» в тексте против
    «Английский» в разборе), тем не менее пропадёт. Своей таблицы соответствий
    ради этого не заводится: она стала бы вторым перечнем имён языков рядом с
    соседским, а промпт просит модель писать имя в той же форме, что и резюме.
    Родному языку поблажки нет: его модель выводит из фамилии кандидата охотнее
    всего, а взамен выброшенного `cv_native.py` поставит язык, на котором текст
    написан, — выведенный из самого текста, а не из имени.
    """
    root = language_root(name)
    return root is None or root.lower() in text


_LEVEL_NEAR_CHARS = 60
"""Сколько знаков за названием языка считается его же строкой.

Уровень стоит вплотную к языку: «Английский — B2», «Английский» и на
следующей строке «свободно». Числом, а не концом строки, потому что перенос
между ними — обычное дело.
"""


def _stops_after(text: str, at: int, others: tuple[str, ...]) -> int:
    """Где кончается кусок, начатый на `at`: у соседнего языка или по мерке."""
    ends = [at + _LEVEL_NEAR_CHARS]
    for other in others:
        root = language_root(other)
        if root is None:
            continue
        spot = text.find(root.lower(), at + 1)
        if spot >= 0:
            ends.append(spot)
    return min(ends)


def _level_windows(text: str, language: str, others: tuple[str, ...]) -> list[str]:
    """Куски текста, в которых может стоять уровень этого языка.

    Каждый начинается с очередного упоминания языка и смотрит только вперёд:
    у двух языков подряд слово соседа стоит выше своего, и назад заглядывать
    нельзя. Кончается кусок раньше мерки, если ближе начинается другой язык:
    «Английский» и строкой ниже «Немецкий — базовый» иначе отдали бы
    английскому чужое слово.

    Упоминаний берутся все, а не первое: корень языка ловится и в
    «англоязычной команде» из раздела «о себе», а настоящий уровень стоит
    ниже. Возьми первое — и честный B1 подменился бы запасным высшим, то есть
    сверка выбросила бы правду.
    """
    root = language_root(language)
    if root is None:
        return []
    windows = []
    at = text.find(root.lower())
    while at >= 0:
        windows.append(text[at: _stops_after(text, at, others)])
        at = text.find(root.lower(), at + 1)
    return windows


def _level_named_in(near: str, word: str) -> bool:
    """Слово уровня стоит в этом куске текста.

    «Свободный график», «продвинутый пользователь Excel», «базовое понимание
    процессов» — слова уровней живут в резюме своей жизнью, и потому кусок
    берётся у самого языка, а не весь текст.

    Дефис по краям запрещён наравне с буквой: «intermediate» сидит внутри
    «upper-intermediate», и без запрета B1 подтверждался бы тем, что на самом
    деле B2. Между словами дефис и пробел, наоборот, равнозначны:
    «Upper-Intermediate» и «Upper Intermediate» — одно написание.

    Кусок смотрится дважды, как есть и со сведёнными омоглифами: обозначение
    шкалы находится во втором виде, а русское слово — только в первом, потому
    что сведение его же и портит.
    """
    loose = r"[\s-]+".join(re.escape(part) for part in re.split(r"[\s-]+", word))
    spelled = rf"(?<![-\w]){loose}(?![-\w])"
    return any(
        re.search(spelled, one) is not None
        for one in (near, fold_homoglyphs(near))
    )


def _level_read_near(windows: list[str]) -> str | None:
    """Уровень, написанный рядом с языком; пусто — там его нет.

    Читается, когда заявленный моделью текстом не подтвердился. Модель
    переводит «начальный» в «Elementary» вопреки наставлению, и заявленного
    слова в русском резюме, конечно, нет — а написанное человеком стоит на
    месте. Читать его вернее, чем уходить в запасной высший.
    """
    for near in windows:
        for spelling, level in LEVELS_BY_SPELLING:
            if _level_named_in(near, spelling):
                return level
        for one in CEFR_LEVELS:
            if _level_named_in(near, one.lower()):
                return one
    return None


def _grounded_level(windows: list[str], level: str) -> str:
    """Уровень языка, если он назван у любого упоминания языка; иначе высший.

    Уровень, названный невнятно — «технический», «письменный», — модель
    заменяет догадкой, и догадка у каждого прогона своя. Спрашивать её с
    текста надо потому же, почему и сам язык: по уровню отбирают вакансии.

    Взамен неподтверждённого ставится высший, и это не поблажка: уровня не
    называет тот, кто в языке уверен, — неуверенный как раз уточняет. Низший
    на его месте отрезал бы человеку все вакансии, где язык нужен, а высший не
    отрезает ничего: лишние объявления человек увидит и отсеет сам.

    Названный словом ищется словом: в тексте стоит «свободно», а не «C1», и
    спрашивать одну лишь шкалу значило бы объявить выдумкой честный перевод.

    Родной уровень не спрашивается: его выводят из языка письма, и слова
    «native» в резюме не бывает.
    """
    if level == NATIVE_LEVEL:
        return level
    named = (level.lower(), *LEVEL_SPELLINGS.get(level, ()))
    if any(_level_named_in(near, word) for near in windows for word in named):
        return level
    return _level_read_near(windows) or CEFR_LEVELS[-1]


# Слова, которыми в резюме называют стек места работы. «Навыки», «Ключевые
# навыки» и «Skills» сюда не входят нарочно: так зовут общий список кандидата,
# и по названию отличают своё от чужого.
_STACK_WORDS = (
    r"(?:\w+\s+)?(?:стек|стэк)|(?:\w+\s+)?технологии|technologies"
    r"|tech\s+stack|stack|инструменты|tools|environment"
)

# Заголовком слово делает двоеточие после него либо своя строка. Одного слова
# мало: «ООО Инновационные технологии безопасности» — имя работодателя, и оно
# разрешало бы работе стек, которого в резюме нет.
_STACK_HEADING_RE = re.compile(
    rf"(?:{_STACK_WORDS})\s*:|^[\s•*-]*(?:{_STACK_WORDS})\s*$",
    re.MULTILINE,
)


def _company_at(lowered: str, company: str, cursor: int) -> int:
    """Где начинается работа этой компании; -1 — названия дальше нет.

    Шапка работы стоит с начала строки, а в «о себе» тот же работодатель
    помянут посреди фразы: «восемь лет в Контуре и Сбере». Возьми первое
    вхождение — и кусок работы съёжится до этого упоминания, отняв у неё
    настоящий стек. Строчного вхождения нет вовсе — берётся любое: у
    «Компания: ООО «Адвант»» название с начала строки не стоит.
    """
    name = re.escape(company.lower())
    heading = re.compile(rf"^[ \t]*({name})", re.MULTILINE)
    found = heading.search(lowered, cursor)
    if found is not None:
        return found.start(1)
    return lowered.find(company.lower(), cursor)


def _job_blocks(text: str, companies: list[str]) -> list[str | None]:
    """Кусок текста на каждую работу: от её названия до названия следующей.

    Пусто — названия в тексте не нашлось: модель его переиначила, и проверять
    такую работу нечем.

    Названия ищутся подряд, каждое следующее — за предыдущим. Первое вхождение
    не годится: о работодателе поминают и в шапке «о себе», и кусок работы
    съёжился бы до этого упоминания, отняв у неё настоящий стек. Тем же
    порядком разводятся две работы в одной компании.

    Кусок начинается сразу ЗА названием: оставь название внутри, и компания,
    назвавшаяся «Технологии Доверия», сама себе разрешила бы стек.

    Последнему куску достаётся весь хвост резюме с разделами, к работе не
    относящимися. Раздел, названный «Технологии:», такая работа зачтёт себе —
    щель известная и неприкрытая.
    """
    lowered = text.lower()
    starts: list[int] = []
    cursor = 0
    for company in companies:
        start = _company_at(lowered, company, cursor)
        starts.append(start)
        if start >= 0:
            cursor = start + len(company)

    blocks: list[str | None] = []
    for number, start in enumerate(starts):
        if start < 0:
            blocks.append(None)
            continue
        opens = start + len(companies[number])
        later = [spot for spot in starts[number + 1:] if spot > start]
        blocks.append(lowered[opens: min(later) if later else len(lowered)])
    return blocks


def _grounded_stack(place, block: str | None) -> list[str]:
    """Стек работы, если резюме объявляет его заголовком; иначе пусто.

    Названия в стеке настоящие — выдумано их место: модель читает «Корректировки
    в 1С» в обязанностях и кладёт 1С в стек, а то и переносит туда весь общий
    список навыков кандидата. Присутствием в тексте такое не ловится, оттого
    спрашивается не название, а заголовок над ним.
    """
    if block is None or _STACK_HEADING_RE.search(block):
        return place.stack
    return []


def _grounded_languages(text: str, languages: list) -> list:
    """Языки, названные в тексте, с уровнем, названным рядом с каждым."""
    named = tuple(lang.language for lang in languages)
    return [
        replace(
            lang,
            level=_grounded_level(
                _level_windows(text, lang.language, named), lang.level
            ),
        )
        for lang in languages
        if _language_named_in(text, lang.language)
    ]


def _grounded_experience(text: str, experience: list) -> list:
    """Места работы со стеком, объявленным заголовком в их же куске текста."""
    blocks = _job_blocks(text, [place.company for place in experience])
    return [
        replace(place, stack=_grounded_stack(place, block))
        for place, block in zip(experience, blocks)
    ]


def _say_dropped(what: str, was, left) -> None:
    for one in [value for value in was if value not in left]:
        logger.info("разбор резюме: %s %r в тексте не назван, выброшен", what, one)


def grounded_in_cv(parsed: ParsedCv, text: str) -> ParsedCv:
    """Разобранное резюме без того, чего его текст не подтверждает."""
    lowered = text.lower()

    grades = [
        grade
        for grade in parsed.profile.grades
        if _any_named_in(lowered, (grade, *GRADE_SPELLINGS.get(grade, ())))
    ]
    formats = _grounded_formats(lowered, parsed.profile.work_format)
    languages = _grounded_languages(lowered, parsed.languages)

    _say_dropped("грейд", parsed.profile.grades, grades)
    _say_dropped("формат", parsed.profile.work_format, formats)
    _say_dropped(
        "язык",
        [lang.language for lang in parsed.languages],
        [lang.language for lang in languages],
    )

    return replace(
        parsed,
        profile=replace(parsed.profile, grades=grades, work_format=formats),
        languages=languages,
        experience=_grounded_experience(text, parsed.experience),
    )
