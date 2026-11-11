"""Тема к готовому письму: шаблон держит код, должность причёсывает модель."""

from adapters.lm_chat import CUT_BY_LIMIT
from backend.llm.letter_subject import letter_subject
from tests.fakes.llm import CHAT, chat_response, data_block, messages_of, provider


async def test_the_model_turns_the_title_into_a_position_inside_the_template():
    client = provider({CHAT: chat_response("Python-разработчик")})

    subject = await letter_subject("Ищем питон-разработчика на фулл-тайм", "Русский", client, "m")

    assert subject == "Отклик на вакансию: Python-разработчик"
    assert "Ищем питон-разработчика на фулл-тайм" in data_block(client.sent[0])
    assert "Язык ответа: Русский" in messages_of(client.sent[0])["system"]


async def test_a_reply_in_another_language_gets_the_international_template_and_language():
    client = provider({CHAT: chat_response("Python Developer")})

    subject = await letter_subject("Ищем питон-разработчика", "Español", client, "m")

    assert subject == "Application for Python Developer"
    assert "Язык ответа: English" in messages_of(client.sent[0])["system"]


async def test_without_a_title_the_model_is_not_asked():
    client = provider({})

    assert await letter_subject(" ", "Русский", client, "m") == "Отклик на вакансию"
    assert client.sent == []


async def test_an_answer_that_is_not_a_position_leaves_the_template_bare():
    client = provider({CHAT: chat_response("Вот должность:\nPython-разработчик")})

    assert await letter_subject("Ищем питониста", "Español", client, "m") == "Job application"


async def test_an_answer_cut_at_the_token_limit_leaves_the_template_bare():
    client = provider({CHAT: chat_response("Senior Python-разра", finish_reason=CUT_BY_LIMIT)})

    assert await letter_subject("Ищем питониста", "Русский", client, "m") == "Отклик на вакансию"


async def test_quotes_a_period_and_a_long_dash_around_the_position_are_cleaned():
    client = provider({CHAT: chat_response("«Senior Python-разработчик — backend».")})

    subject = await letter_subject("Ищем сеньора", "Русский", client, "m")

    assert subject == "Отклик на вакансию: Senior Python-разработчик - backend"
