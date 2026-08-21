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

logger = logging.getLogger(__name__)

PURPOSE = "validate_language_fit"

LANGUAGE_FIT_PROMPT = """Ты проверяешь Telegram-пост о вакансии по ОДНОМУ критерию: требует ли работа языка, которым кандидат не владеет на нужном уровне.

""" + VERDICT_SCOPE + """

КАНДИДАТ (это и только это — мерка):
- Языки (название — уровень CEFR; "native" = родной): {LANGUAGE_REQUIREMENTS}

Если {LANGUAGE_REQUIREMENTS} = «—» (языки не указаны) — блокера нет вовсе, ставь fit.

reject ставится ТОЛЬКО если в тексте ЯВНО найдено языковое требование выше уровня кандидата или язык, которого у него нет. Явное требование — это:
- указанный уровень: A1/A2/B1/B2/C1/C2, Upper-Intermediate, Advanced, Fluent, «свободный устный», «spoken»;
- «<язык>-speaking team», «клиент/команда говорит только на <язык>»;
- «ежедневные митинги/созвоны/standup'ы на <язык>»;
- «interviews in <язык>».

КРИТИЧНО — что НЕ является языковым требованием:
- заимствованные англицизмы в русскоязычном тексте: «Code Review», «Scrum meetings», «стейкхолдеры», «ownership», «фасилитировать», «backlog», «performance review», «kick-off», «1-on-1», «soft skills», «tech-lead», «митинги», «созвоны», «стендапы». Это стандартные IT-термины, ими говорят русскоязычные команды между собой;
- «руководящие» обязанности (тимлид, ведёт код-ревью, общается со стейкхолдерами) — это про роль, а не про язык;
- английские названия технологий и инструментов (PostgreSQL, FastAPI, Kafka, Jira, Figma);
- английские названия должностей в заголовке (Senior X Developer, Team Lead, Marketing Manager);
- язык, на котором написан сам пост: русский или английский текст поста НЕ определяет язык работы;
- знание языка «будет плюсом», «желательно», «для чтения документации».

Если ни уровня, ни «<язык>-speaking», ни «митингов на <язык>», ни «interviews in <язык>» в тексте нет — reject ЗАПРЕЩЁН.

Всё остальное — не твой критерий: профессия, стек, формат работы, страна офиса, зарплата, опыт. В reason им не место.

""" + ANSWER_RULES + """

--- ПРИМЕРЫ ФОРМАТА (НЕ КОПИРУЙ reason ДОСЛОВНО) ---

Пример 1 (reject — явный уровень и созвоны на языке):
LANGUAGE_REQUIREMENTS: Русский — native, Английский — B1. Текст: "...daily standups in English with the US team, English Upper-Intermediate required..."
Ответ: {"verdict": "reject", "reason": "Требуется английский на уровне Upper-Intermediate и ежедневные standup'ы на английском."}

Пример 2 (reject — язык, которого у кандидата нет вовсе):
LANGUAGE_REQUIREMENTS: Русский — native, Английский — B2. Текст: "Команда общается на немецком, встречи с клиентом на немецком языке."
Ответ: {"verdict": "reject", "reason": "Работа ведётся на немецком: общение команды и встречи с клиентом на этом языке."}

Пример 3 (fit — англицизмы без языкового требования):
LANGUAGE_REQUIREMENTS: Русский — native, Английский — B1. Текст: "Тимлиду нужно: руководить командой, проводить Code Review, фасилитировать Scrum meetings. Требования: 5 лет опыта."
Ответ: {"verdict": "fit", "reason": "Языковых требований в тексте нет: названы только обязанности тимлида и опыт."}

Пример 4 (fit — англоязычный пост без требования уровня):
LANGUAGE_REQUIREMENTS: Русский — native, Английский — B2. Текст: "Backend Engineer. We're a fully remote product team. You'll work on our payments service in Python."
Ответ: {"verdict": "fit", "reason": "The post states no language requirement — only the role and the product stack."}

Пример 5 (fit — язык только для чтения):
LANGUAGE_REQUIREMENTS: Русский — native, Английский — B1. Текст: "...будет плюсом: знание немецкого для чтения исследований..."
Ответ: {"verdict": "fit", "reason": "Немецкий назван как «будет плюсом» для чтения исследований, а не как требование."}

--- КОНЕЦ ПРИМЕРОВ ---

Напоминание: нет в тексте явной языковой формулировки — fit. Заимствованные термины и язык самого поста требованием не считаются."""


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
