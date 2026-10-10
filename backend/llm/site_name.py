"""Имя сервиса по адресу его сайта — так, как его называют люди."""

import logging

import httpx

from adapters.lm_chat import ChatRequest, chat
from backend.llm.external import external_block

logger = logging.getLogger(__name__)

# Бюджет — как у соседей: рассуждающая модель тратит его на размышление до
# ответа, и короткий ответ не значит короткого бюджета.
MAX_SITE_NAME_TOKENS = 1200

# Длиннее имя сервиса не бывает; длиннее — уже описание сайта, а не имя.
MAX_NAME_CHARS = 40

SITE_NAME_PROMPT = """Задача — назвать сервис по адресу его сайта так, как этот сервис называют люди: его торговое имя, которым сервис подписывает себя как бренд и которым его называют в речи и в новостях о нём, в том написании, каким пишет его сам сервис.

Адрес сайта и подсказки с его главной страницы придут отдельным сообщением как данные. Подсказки — то, как страница называет себя в шапке и в заголовке вкладки; рядом с именем там обычно стоит описание страницы или адрес сайта, а имя из них выбирается одно.

Ответ — одна строка, в которой стоит только это имя."""


def _request(host: str, hints: list[str]) -> ChatRequest:
    shown = "\n".join([f"Адрес: {host}", "Подсказки со страницы:", *(f"- {hint}" for hint in hints)])
    return ChatRequest(
        purpose="site_name",
        messages=[
            {"role": "system", "content": SITE_NAME_PROMPT},
            {"role": "user", "content": external_block(
                shown, "адрес сайта и подсказки с его главной страницы", "Ответ — имя сервиса.",
            )},
        ],
        max_tokens=MAX_SITE_NAME_TOKENS,
    )


async def ask_site_name(host: str, hints: list[str], client: httpx.AsyncClient, model: str) -> str | None:
    """Имя сервиса со слов модели; пусто — не ответила или ответила не именем.

    Именем считается одна короткая строка: разговор вокруг имени в название
    агрегатора не годится, и тогда имя берётся из подсказок.
    """
    answer = await chat(client, model, _request(host, hints), logger)
    text = (answer.text or "").strip()
    if not text or "\n" in text or len(text) > MAX_NAME_CHARS:
        if answer.text:
            logger.info("site_name: ответ модели не похож на имя: %r", answer.text[:120])
        return None
    return text
