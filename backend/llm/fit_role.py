"""Один вопрос о вакансии: та ли это профессия.

Кандидат приходит сюда двумя строками — профессия и навыки, — и больше ничем.
Ни локации, ни языков, ни предпочтений, ни грейда с форматом зов не видит:
о том, чего ему не давали, он не ошибётся.
"""


import logging

import httpx

from backend.payloads import FitValidation, ParsedVacancy

from backend.llm.candidate import (
    CandidateProfile,
    format_known_skills,
    format_text,
)
from backend.llm.fit import ANSWER_RULES, VERDICT_SCOPE, FitQuestion, ask_fit, vacancy_block

logger = logging.getLogger(__name__)

PURPOSE = "validate_role_fit"

ROLE_FIT_PROMPT = """Ты проверяешь Telegram-пост о вакансии по ОДНОМУ критерию: совпадает ли профессия (основная роль) вакансии с профессией кандидата.

""" + VERDICT_SCOPE + """

КАНДИДАТ (это и только это — мерка):
- Профессия / основная роль: {CANDIDATE_TITLE}
- Основной стек / ключевые скилы (формат: каноническое_имя — алиасы):
{CANDIDATE_SKILLS}

ПРИНЦИП ОЦЕНКИ:
- Сравнение симметричное: с одной стороны — то, что РЕАЛЬНО НАПИСАНО в посте; с другой — две строки выше. Никаких допущений ни про того, ни про другого.
- Если {CANDIDATE_TITLE} = «—» (профессия не указана) — блокера нет вовсе, ставь fit.

reject ставится ТОЛЬКО когда верно одно из двух:
1. Основная роль ВАКАНСИИ принадлежит другой профессиональной области (бэкенд vs фронтенд vs дизайнер vs маркетолог vs DevOps vs дата-сайентист vs QA vs менеджер и т. п.).
2. Основной язык/инструмент вакансии не совпадает с основным стеком кандидата, а его скилы упомянуты только как «будет плюсом», «приветствуется», эпизодически.

НЕ блокер:
- вакансия упоминает основной стек кандидата на равных с другими языками/инструментами («Python + Go микросервисы», «Vue/React фронт», «Figma + Sketch»);
- вариативная роль (full-stack, generalist), где зона ответственности кандидата покрыта;
- незнакомое название должности при знакомых обязанностях: решает описание работы, а не заголовок.

Всё остальное — не твой критерий. Размер компании, зарплата, формат работы, язык общения, страна офиса, требуемый опыт, отсутствие описания компании — ни одно из этого не повод для reject здесь, и в reason им не место.

""" + ANSWER_RULES + """

--- ПРИМЕРЫ ФОРМАТА (НЕ КОПИРУЙ reason ДОСЛОВНО; примеры намеренно из разных профессий — логика не зависит от домена) ---

Пример 1 (reject — другая профессиональная область):
CANDIDATE_TITLE: UX/UI-дизайнер. Текст: "Ищем SMM-менеджера: ведение соцсетей, контент-план, работа с блогерами."
Ответ: {"reason": "Основная роль вакансии — SMM-менеджер: ведение соцсетей и контент-план.", "verdict": "reject"}

Пример 2 (reject — основной инструмент чужой, навык кандидата только «плюс»):
CANDIDATE_TITLE: Mobile-разработчик. CANDIDATE_SKILLS: Kotlin, Swift. Текст: "Основной стек — C#/Unity, опыт с мобильными языками будет плюсом."
Ответ: {"reason": "Основной стек вакансии — C#/Unity; мобильные языки заявлены только как «плюс».", "verdict": "reject"}

Пример 3 (fit — стек кандидата на равных с другим):
CANDIDATE_TITLE: Бэкенд-разработчик. CANDIDATE_SKILLS: Python. Текст: "Микросервисы на Python и Go, команда продукта."
Ответ: {"reason": "Вакансия про микросервисы на Python и Go — основной стек назван на равных.", "verdict": "fit"}

Пример 4 (fit — роль названа, критерий не нарушен):
CANDIDATE_TITLE: Флорист. Текст: "Ищем флориста в студию, пишите @hr_anna"
Ответ: {"reason": "Роль вакансии — флорист: «Ищем флориста в студию».", "verdict": "fit"}

--- КОНЕЦ ПРИМЕРОВ ---

Напоминание: единственный твой вопрос — профессия. Не видишь в тексте слов, из которых следует ДРУГАЯ профессиональная область, — ставь fit."""


def _prompt_for(profile: CandidateProfile) -> str:
    """Наставление с подставленными мерками кандидата."""
    return (
        ROLE_FIT_PROMPT
        .replace("{CANDIDATE_TITLE}", format_text(profile.title))
        .replace("{CANDIDATE_SKILLS}", format_known_skills(profile.known_skills))
    )


async def validate_role_fit(
    parsed: ParsedVacancy, raw_text: str, client: httpx.AsyncClient, model: str,
    *, profile: CandidateProfile,
) -> tuple[FitValidation | None, str | None]:
    """Та ли это профессия и, если не спросилось, почему."""
    logger.debug("%s: title=%r", PURPOSE, parsed.title)
    return await ask_fit(
        FitQuestion(purpose=PURPOSE, prompt=_prompt_for(profile)),
        vacancy_block(parsed, raw_text),
        client,
        model,
    )
