"""Один вопрос о вакансии: требует ли она языка, которого у кандидата нет.

Кандидат приходит сюда одной строкой — языки с уровнями. Ни профессии, ни
локации, ни предпочтений зов не видит.

Заслон на выдуманное обоснование стоит здесь, а не общим: приметы у него
языковые — уровень CEFR и ежедневные созвоны, — и другим двум зовам ловить
ими нечего.
"""


import logging

import httpx

from backend.payloads import FitValidation, ParsedVacancy

from backend.llm.candidate import CandidateProfile, format_languages
from backend.llm.fit import ANSWER_RULES, VERDICT_SCOPE, FitQuestion, ask_fit, vacancy_text
from backend.llm.hallucination import looks_hallucinated
from backend.llm.rules import LEVEL_MARKERS

logger = logging.getLogger(__name__)

PURPOSE = "validate_language_fit"

LANGUAGE_FIT_PROMPT = """Ты проверяешь объявление о вакансии по ОДНОМУ критерию: требует ли работа языка, которым кандидат не владеет на нужном уровне.

""" + VERDICT_SCOPE + """

КАНДИДАТ (это и только это — мерка):
- Языки кандидата (название — уровень по шкале A1–C2; "native" = родной): {LANGUAGE_REQUIREMENTS}

Если языки кандидата — «—», блокера нет вовсе, ставь fit.

reject ставится, только если текст прямо называет язык обязательным для работы — уровнем, словами «требуется / обязателен / required / must» или тем, что на нём идёт работа (команда, клиенты, встречи, собеседования), — а у кандидата этого языка нет или уровень ниже. Словесные уровни читаются по шкале: """ + LEVEL_MARKERS + """; «native» выше любого. Язык назван обязательным без уровня — нужен не ниже B1. Шкала нужна только для сравнения: в reason уровень, частоту и формат встреч пиши ровно словами поста («свободный английский», «созвоны каждый день»), не переводя в шкалу.

Языковым требованием не являются:
- профессиональные заимствования внутри текста на другом языке («Code Review», «backlog», «бриф», «KPI», «су-шеф», «дедлайн») — это термины ремесла;
- обязанности общаться и руководить без названного языка — это про роль;
- названия инструментов, программ, брендов и должностей на другом языке (Excel, AutoCAD, Figma, Store Manager);
- язык, на котором написан сам пост;
- знание языка «будет плюсом», «желательно», «для чтения документации».

Всё остальное — не твой критерий: профессия, стек, формат работы, страна офиса, зарплата, опыт. В reason им не место.

""" + ANSWER_RULES + """

--- ПРИМЕРЫ ФОРМАТА (НЕ КОПИРУЙ reason ДОСЛОВНО) ---

Пример 1 (reject — уровень и встречи на языке):
Языки кандидата: Испанский — native, Английский — B1. Текст: "...daily meetings in English with the client, English Upper-Intermediate required..."
Ответ: {"reason": "Upper-Intermediate English is required, with daily meetings in English.", "verdict": "reject"}

Пример 2 (reject — работа идёт на языке, которого у кандидата нет):
Языки кандидата: Польский — native, Английский — A2. Текст: "Команда и клиенты общаются на немецком, собеседование тоже на немецком."
Ответ: {"reason": "Работа ведётся на немецком: общение команды, клиентов и собеседование.", "verdict": "reject"}

Пример 3 (reject — язык назван обязательным без уровня, а у кандидата ниже B1):
Языки кандидата: Арабский — native, Немецкий — A2. Текст: "Требуется знание немецкого языка."
Ответ: {"reason": "Требуется знание немецкого языка.", "verdict": "reject"}

Пример 4 (fit — заимствования без языкового требования):
Языки кандидата: Казахский — native, Русский — C1. Текст: "Су-шеф на кухню ресторана: составление меню, бриф с поставщиками, контроль KPI смены. Опыт от 3 лет."
Ответ: {"reason": "Языковых требований в тексте нет: названы только обязанности су-шефа и опыт.", "verdict": "fit"}

Пример 5 (fit — пост на другом языке без требования):
Языки кандидата: Турецкий — native, Английский — B2. Текст: "Store Manager. We're a retail chain in the city centre. You'll run a team of 12 and handle stock."
Ответ: {"reason": "The post states no language requirement, only the role and the team.", "verdict": "fit"}

Пример 6 (fit — язык как «будет плюсом»):
Языки кандидата: Испанский — native, Английский — C1. Текст: "...будет плюсом: знание немецкого для чтения документации..."
Ответ: {"reason": "Немецкий назван как «будет плюсом» для чтения документации, а не как требование.", "verdict": "fit"}

--- КОНЕЦ ПРИМЕРОВ ---"""


def _prompt_for(profile: CandidateProfile) -> str:
    """Наставление с подставленными языками кандидата."""
    return LANGUAGE_FIT_PROMPT.replace(
        "{LANGUAGE_REQUIREMENTS}", format_languages(profile.languages)
    )


def _without_invented_language(
    validation: FitValidation, raw_text: str, profile: CandidateProfile
) -> FitValidation:
    """Обезвредить отказ, обоснованный языком, которого в объявлении нет.

    Выдуманное обоснование отказа переводит вердикт в «годится»: пропустить
    вакансию к ручному просмотру дешевле, чем потерять подходящую.
    """
    if validation.verdict != "reject" or validation.reason is None:
        return validation
    marker = looks_hallucinated(validation.reason, raw_text, profile)
    if marker is None:
        return validation
    logger.warning(
        "%s: обоснование отказа не найдено в тексте (маркер %s), считаю "
        "вакансию годной. reason=%r",
        PURPOSE, marker, validation.reason,
    )
    return FitValidation(verdict="fit", reason=None)


async def validate_language_fit(
    parsed: ParsedVacancy, raw_text: str, client: httpx.AsyncClient, model: str,
    *, profile: CandidateProfile,
) -> tuple[FitValidation | None, str | None]:
    """Требует ли вакансия чужого языка и, если не спросилось, почему."""
    logger.debug("%s: title=%r", PURPOSE, parsed.title)
    validation, trouble = await ask_fit(
        FitQuestion(purpose=PURPOSE, prompt=_prompt_for(profile)),
        vacancy_text(raw_text),
        client,
        model,
    )
    if validation is None:
        return None, trouble
    return _without_invented_language(validation, raw_text, profile), None
