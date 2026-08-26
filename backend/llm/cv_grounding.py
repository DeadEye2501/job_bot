"""Что в разобранном резюме не подтверждается его же текстом.

Запрет «не выдумывай» стоит в промпте, но держат его не все модели: на четырёх
миллиардах параметров резюме без единого слова о грейде возвращается с
`middle` и `senior`, а резюме без раздела языков — с родным языком, выведенным
из имени кандидата. Слова в промпте это не лечит: пробовали, помогло только
там, где выдумку было чем заменить.

Сверяются два поля из всей анкеты, и оба — по цене ошибки. Грейд и язык
участвуют в отборе вакансий: выдуманный `senior` уводит от подходящих
объявлений, выдуманный язык — приводит к неподходящим. Остальное выдумкой
портится куда меньше, а сверять его было бы нечем: достижение своими словами
пересказано законно и дословно в тексте не ищется.

Сосед по замыслу — `hallucination.py`: там тем же вопросом проверяют
обоснование вердикта по вакансии. Отличает предмет: там объявление и приговор
о нём, здесь резюме и анкета из него. Разбор названия языка со склонениями у
них общий и живёт у соседа.
"""

import logging
import re
from dataclasses import replace

from backend.domain.taxonomy import GRADE_SPELLINGS
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


def _grade_named_in(text: str, grade: str) -> bool:
    # «Ё» в резюме пишут через раз, и «стажер» — то же слово, что «стажёр». Не
    # своди их — и настоящее звание объявлялось бы выдуманным.
    plain = text.replace("ё", "е")
    return any(
        _spelled_in(plain, word.replace("ё", "е"))
        for word in (grade, *GRADE_SPELLINGS.get(grade, ()))
    )


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
    """
    root = language_root(name)
    return root is None or root.lower() in text


def grounded_in_cv(parsed: ParsedCv, text: str) -> ParsedCv:
    """Разобранное резюме без грейдов и языков, которых в тексте нет."""
    lowered = text.lower()

    grades = [
        grade for grade in parsed.profile.grades if _grade_named_in(lowered, grade)
    ]
    languages = [
        lang for lang in parsed.languages if _language_named_in(lowered, lang.language)
    ]

    for grade in set(parsed.profile.grades) - set(grades):
        logger.info("разбор резюме: грейд %r в тексте не назван, выброшен", grade)
    for lang in parsed.languages:
        if lang not in languages:
            logger.info(
                "разбор резюме: язык %r в тексте не назван, выброшен", lang.language
            )

    return replace(
        parsed,
        profile=replace(parsed.profile, grades=grades),
        languages=languages,
    )
