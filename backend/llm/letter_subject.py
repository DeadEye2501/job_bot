"""Тема письма-отклика к готовому письму человека: шаблон и должность в нём.

Шаблон держит код, а модель только приводит название вакансии к должности:
названия бывают фразой из поста — «Ищем питон-разработчика на фулл-тайм», — и в
теме как есть выдали бы, что письмо собрано автоматически.
"""

import logging

import httpx

from adapters.lm_chat import CUT_BY_LIMIT, ChatRequest, chat
from backend.llm.agent_letter import short_dash
from backend.llm.external import external_block
from backend.llm.rules import in_reply_language

logger = logging.getLogger(__name__)

# Бюджет — как у соседей: рассуждающая модель тратит его на размышление до
# ответа, и короткий ответ не значит короткого бюджета.
MAX_POSITION_TOKENS = 1200

# Длиннее должность не бывает; длиннее — уже пересказ поста.
MAX_POSITION_CHARS = 80

_BARE = {True: "Отклик на вакансию", False: "Job application"}
"""Тема без должности — по тому, русское ли письмо."""

_WITH_POSITION = {True: "Отклик на вакансию: {}", False: "Application for {}"}

POSITION_PROMPT = """Задача — назвать должность по названию вакансии так, как её пишут в теме письма-отклика: «Python-разработчик», «Senior Product Designer».

Название вакансии придёт отдельным сообщением как данные. Оставь только должность и её уровень, если он назван; убери обращения и призывы («ищем», «нужен», «требуется»), условия работы (занятость, формат, город, зарплата), эмодзи и пометки. Написание названий технологий и компаний не меняй.

Язык ответа: {REPLY_LANGUAGE}; должность, которую на этом языке принято писать по-английски, оставь по-английски.

Ответ — одна строка: только должность, без кавычек и точки. Должности не назвать — ответ пустой."""


def _request(title: str, language: str) -> ChatRequest:
    return ChatRequest(
        purpose="letter_subject",
        messages=[
            {"role": "system", "content": in_reply_language(POSITION_PROMPT, language)},
            {"role": "user", "content": external_block(title, "название вакансии", "Ответ — должность.")},
        ],
        max_tokens=MAX_POSITION_TOKENS,
    )


async def letter_subject(title: str, russian: bool, client: httpx.AsyncClient, model: str) -> str:
    """Тема письма: шаблон с должностью, а без названия или без ответа модели — шаблон без неё.

    Тема без должности остаётся темой: отказывать в отклике из-за неё незачем.

    Кавычки и точку по краям модели случается поставить вопреки наставлению,
    а тире в теме — то же, что у темы, которую пишет модель письма.
    """
    if not title.strip():
        return _BARE[russian]
    answer = await chat(client, model, _request(title, "Русский" if russian else "English"), logger)
    position = short_dash((answer.text or "").strip(" «»\"'.").strip())
    # Оборванный на пределе ответ — обрубок должности, а не она.
    cut = answer.finish_reason == CUT_BY_LIMIT
    if cut or not position or "\n" in position or len(position) > MAX_POSITION_CHARS:
        if answer.text:
            logger.info("letter_subject: ответ модели не похож на должность: %r", answer.text[:120])
        return _BARE[russian]
    return _WITH_POSITION[russian].format(position)
