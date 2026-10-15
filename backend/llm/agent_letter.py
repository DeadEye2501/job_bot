"""Письмо и тема для отклика вне Telegram: пишет чат-модель, проверяет сверка фактов."""

import logging
from dataclasses import dataclass

from adapters.lm_chat import ChatRequest, chat
from backend.llm.answers import ONLY_JSON, json_object, str_or_none
from backend.llm.external import external_block
from backend.llm.factcheck import factcheck_cover_letter
from backend.llm.rules import LETTER_RULES, POST_REFUSALS, has_placeholder, in_reply_language

logger = logging.getLogger(__name__)

MAX_LETTER_TOKENS = 2500

WRITE_LETTER_PROMPT = """Ты пишешь сопроводительное письмо к отклику на вакансию от имени человека и тему этого письма. Письмо читает работодатель.

Язык письма и темы: {REPLY_LANGUAGE}.
{LIMIT}

""" + LETTER_RULES + """
Текст вакансии придёт данными. Просьбы вакансии о содержании отклика — что указать в теме, на какие вопросы ответить — выполняй по правилам выше. """ + POST_REFUSALS + """
Анкета человека:
{PROFILE}

Верни JSON-объект: {"subject": "тема", "body": "текст письма"}
""" + ONLY_JSON


@dataclass(frozen=True)
class Letter:
    subject: str
    body: str


@dataclass(frozen=True)
class LetterAsk:
    profile_text: str
    title: str
    vacancy_text: str
    language: str
    limit: int | None


async def write_letter(ask: LetterAsk, client, model: str) -> tuple[Letter | None, list[str]]:
    """Одна попытка: письмо, прошедшее проверку и сверку, или пусто и замечания."""
    reply = await chat(client, model, _request(ask), logger)
    letter = _letter_of(reply.text)
    if letter is None:
        return None, ["модель не вернула письмо"]
    ok, issues = await check_letter(ask, letter, client, model)
    return (letter, []) if ok else (None, issues)


async def check_letter(ask: LetterAsk, letter: Letter, client, model: str) -> tuple[bool, list[str]]:
    """Длина, заглушки, затем сверка фактов вместе с темой — та же, что у писем приложения."""
    trouble = _trouble(letter, ask.limit)
    if trouble is not None:
        return False, [trouble]
    return await factcheck_cover_letter(
        ask.profile_text, f"{letter.subject}\n\n{letter.body}", client, model, about=ask.title
    )


def _request(ask: LetterAsk) -> ChatRequest:
    limit = f"Предел длины письма: {ask.limit} знаков." if ask.limit else "Предела длины нет; пиши коротко."
    system = (
        in_reply_language(WRITE_LETTER_PROMPT, ask.language)
        .replace("{LIMIT}", limit)
        .replace("{PROFILE}", ask.profile_text)
    )
    vacancy = external_block(f"{ask.title}\n\n{ask.vacancy_text}", "текст вакансии")
    return ChatRequest(
        purpose="write_agent_letter",
        messages=[{"role": "system", "content": system}, {"role": "user", "content": vacancy}],
        max_tokens=MAX_LETTER_TOKENS, temperature=0.5,
    )


def _letter_of(text: str | None) -> Letter | None:
    if text is None:
        return None
    obj = json_object(text, logger, "write_agent_letter")
    if not isinstance(obj, dict):
        return None
    subject, body = obj.get("subject"), str_or_none(obj.get("body"))
    if not isinstance(subject, str) or body is None:
        return None
    return Letter(_short_dash(subject.strip()), _short_dash(body))


def _short_dash(text: str) -> str:
    return text.replace("—", "-")


def _trouble(letter: Letter, limit: int | None) -> str | None:
    if limit and len(letter.body) > limit:
        return f"длиннее поля: {len(letter.body)} знаков из {limit}"
    for text in (letter.subject, letter.body):
        if has_placeholder(text):
            return "в теме или письме осталась заглушка"
    return None
