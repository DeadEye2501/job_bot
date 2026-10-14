"""Общее у зовов о пригодности: чем спросить модель и как прочесть ответ.

Сами вопросы живут порознь — роль, языки, место, свободные предпочтения, — и наставление
у каждого своё, про один критерий. Разведены они потому, что зов не может
ошибиться о том, чего ему не давали: видя шесть критериев и весь профиль разом,
модель применяла запрет из одного к предмету другого.

Здесь остаётся то, что у всех одинаково: бюджет токенов, повтор с запасом,
разбор ответа и заслон на обоснование, пересказывающее данные кандидата.
"""


import logging
from collections.abc import Callable
from dataclasses import dataclass

import httpx

from adapters.lm_chat import ChatRequest, chat

from backend.payloads import FitValidation, ParsedVacancy

from backend.incoming import normalize_enum
from backend.llm.answers import (
    ONLY_JSON,
    json_object,
    read_with_a_second_try,
    str_or_none,
)
from backend.llm.external import external_block
from backend.llm.hallucination import breaks_reason_style
from backend.llm.rules import VACANCY_TEXT_CHARS

# Бюджет токенов на вердикт пригодности — тот же, что у соседей по причине,
# описанной в `hr_reply.MAX_CLASSIFY_TOKENS`: рассуждающая модель тратит их на
# размышление до ответа. Четырёхсот не хватало, и с тех пор как обрыв здесь
# перестал считаться отказом, упёршаяся в предел вакансия не уходит в «не
# подходит», а остаётся неразобранной — то есть разбирается заново при каждом
# запуске и не разберётся уже никогда. Оборвавшийся ответ переспрашивается с
# запасом (`ROOMIER_FIT_TOKENS`), и только если не хватило и его, вердикт
# сдаётся, а зовущий записывает строку с названной причиной.
MAX_FIT_TOKENS = 1200
ROOMIER_FIT_TOKENS = 2400

ASKED_VERDICTS: tuple[str, ...] = ("fit", "reject")
"""Что может ответить зов о пригодности.

«Мусор» сюда не входит, хотя перечисление вердиктов его знает: вакансия ли
это, решает зов о жанре, и решает раньше. Прими мы «мусор» от зова о роли или
о языках — вакансию удалил бы тот, кого о жанре не спрашивали, а вернуть её
нечем: курсор канала уже ушёл вперёд.
"""

logger = logging.getLogger(__name__)


# Обоснование стоит в ответе раньше вердикта, и это не оформление. Не
# рассуждающая модель выбирает вердикт первым же токеном ответа, а обоснование
# подгоняет под уже выбранное — вплоть до того, что сама пишет про нарушенный
# запрет и тут же заключает «не нарушается». Написанное раньше вердикта
# обоснование служит рассуждением: назвав требование словами, модель выводит
# вердикт из него. Разбору ответа порядок безразличен — там объект, а не строка.
ANSWER_RULES = """Формат ответа: ТОЛЬКО JSON-объект.
{"reason": "...", "verdict": "fit" | "reject"}

ПОРЯДОК ОБЯЗАТЕЛЕН: сначала reason, потом verdict. Сперва разбери присланный текст словами, а вердиктом назови тот, который из разобранного следует.

reason ОБЯЗАТЕЛЕН для обоих вердиктов.
- Для reject reason ФОРМУЛИРУЕТСЯ КАК ТРЕБОВАНИЕ ВАКАНСИИ, а не как сравнение с кандидатом. Не пересказывай данные кандидата — он их знает; ему нужно понять, ЧТО требует ВАКАНСИЯ, чтобы решить, можно ли с этим работать.
- Для fit — 1 предложение с опорой на присланный текст.
- reason ОБЯЗАН ссылаться на КОНКРЕТНЫЕ слова, фразы или факты, ФИЗИЧЕСКИ ПРИСУТСТВУЮЩИЕ в присланном тексте. Не можешь процитировать место, подтверждающее блокер, — ставь "fit". Лучше fit-ошибка (человек отфильтрует руками), чем выдуманная причина отказа.
- ЗАПРЕЩЕНО копировать reason из примеров: они показывают формат и логику, а слова бери из присланного текста.
- Язык reason — ТОТ ЖЕ, что у исходного поста (русский пост → русский reason; English post → English reason).
""" + ONLY_JSON

VERDICT_SCOPE = """Ты отвечаешь ровно на один вопрос — тот, что описан ниже. Других критериев у тебя нет.

Пост уже признан вакансией другим зовом: «это не вакансия» — не твой вердикт и не твоя забота. Остальные критерии пригодности проверяют другие зовы, и вмешиваться в них запрещено: не поминай в reason ничего, о чём тебя не спрашивали."""


@dataclass(frozen=True)
class FitQuestion:
    """Один вопрос о пригодности: чем спрашивать и как звать его в журнале.

    Имя зова едет и в запрос к провайдеру, и в записи журнала: по нему в
    логах видно, который из них ответил несуразицей.
    """

    purpose: str
    prompt: str


def vacancy_block(parsed: ParsedVacancy, raw_text: str) -> str:
    """Вакансия с разобранными полями и куском исходника.

    Исходник нужен затем, чтобы обоснование отказа ссылалось на настоящие
    слова вакансии, а не на примеры из наставления. Поля даются не всякому
    зову: языкам и предпочтениям хватает текста, а грейд с форматом в полях
    сбивали бы их на чужой критерий.
    """
    return (
        "Распарсенные поля:\n"
        f"- title: {parsed.title!r}\n"
        f"- description: {parsed.description!r}\n"
        f"- company_name: {parsed.company_name!r}\n"
        f"- stack_required: {parsed.stack_required}\n"
        f"- stack_preferred: {parsed.stack_preferred}\n\n"
        "Оригинальный текст вакансии:\n"
        f"{raw_text[:VACANCY_TEXT_CHARS]}"
    )


def vacancy_text(raw_text: str) -> str:
    """Одна вакансия текстом, без разобранных полей."""
    return "Оригинальный текст вакансии:\n" f"{raw_text[:VACANCY_TEXT_CHARS]}"


def text_fit_question(purpose: str, prompt_for: Callable) -> Callable:
    """Зов о пригодности, которому нужен только текст поста и своё наставление.

    Зовы такого вида отличаются лишь целью и наставлением (`prompt_for` строит
    его из профиля кандидата), поэтому и собираются здесь одним телом.
    """

    async def validate(
        parsed: ParsedVacancy, raw_text: str, client: httpx.AsyncClient, model: str,
        *, profile,
    ) -> tuple[FitValidation | None, str | None]:
        logger.debug("%s: title=%r", purpose, parsed.title)
        return await ask_fit(
            FitQuestion(purpose=purpose, prompt=prompt_for(profile)),
            vacancy_text(raw_text), client, model,
        )

    return validate


def _parse_fit_validation(answer: str, purpose: str) -> FitValidation | None:
    data = json_object(answer, logger, purpose)
    if data is None:
        return None

    verdict = normalize_enum(data.get("verdict"), ASKED_VERDICTS)
    if verdict is None:
        return None

    return FitValidation(verdict=verdict, reason=str_or_none(data.get("reason")))


def _request(question: FitQuestion, about: str, max_tokens: int) -> ChatRequest:
    """Что спросить у модели: наставление зова и вакансия к проверке."""
    user_msg = external_block(
        about,
        "вакансия к проверке (настоящая, не пример из промпта)",
        'Верни JSON {"reason": ..., "verdict": ...} — сначала reason. reason '
        "ссылается на конкретные слова и факты из текста выше.",
    )
    return ChatRequest(
        purpose=question.purpose,
        messages=[
            {"role": "system", "content": question.prompt},
            {"role": "user", "content": user_msg},
        ],
        max_tokens=max_tokens,
    )


def _without_candidate_data(
    validation: FitValidation, purpose: str
) -> FitValidation:
    """Погасить обоснование, пересказывающее данные кандидата.

    Гасится обоснование, а вердикт остаётся любым: модель написала не о том,
    но отвергла по делу. Переверни мы и его, откликатель отправил бы
    письмо живому HR по вакансии, отвергнутой правильно.
    """
    if validation.verdict != "reject" or validation.reason is None:
        return validation
    style = breaks_reason_style(validation.reason)
    if style is None:
        return validation
    logger.warning(
        "%s: обоснование говорит о кандидате, а не о вакансии (примета %s), "
        "гашу обоснование. reason=%r",
        purpose, style, validation.reason,
    )
    return FitValidation(verdict=validation.verdict, reason=None)


async def ask_fit(
    question: FitQuestion, about: str, client: httpx.AsyncClient, model: str,
) -> tuple[FitValidation | None, str | None]:
    """Спросить один вопрос о пригодности; пусто — спросить не вышло.

    Причина отделена от пустого вердикта нарочно, как и у разбора: «модель не
    ответила» — не приговор вакансии, и помечать по нему строку разобранной
    нельзя, иначе лежащий полчаса провайдер уводит в «не подходит» всё, что
    пришло за это время.

    Неразобранный ответ причиной не считается: модель ответила, а сказала
    несуразицу — зовущий считает это отказом и шлёт вакансию на ручной
    просмотр.
    """

    def read(answer: str) -> FitValidation | None:
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("%s: answer=%r", question.purpose, answer)
        return _parse_fit_validation(answer, question.purpose)

    validation, trouble = await read_with_a_second_try(
        lambda room: chat(client, model, _request(question, about, room), logger),
        read,
        (MAX_FIT_TOKENS, ROOMIER_FIT_TOKENS),
        (logger, question.purpose),
    )
    if validation is None:
        return None, trouble
    return _without_candidate_data(validation, question.purpose), None
