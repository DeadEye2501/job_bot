"""Следствия ответа модели о жанре поста.

Вопрос здесь один — зовёт ли автор на работу или предлагает себя, — и цена
ошибки несимметрична: по ответу «не вакансия» строку удаляют без возврата, а
по «вакансия» пост едет дальше к оценщику и может кончиться письмом живому
человеку. Поэтому вердикт без обоснования не берётся вовсе: проверить его
нечем, а вердиктом без слов модель как раз и пропускает резюме.
"""

import httpx

from backend.llm.genre import classify_post_genre
from tests.fakes.llm import CHAT, chat_json, chat_response, messages_of, provider


async def _asked(answer: httpx.Response, text: str = "Ищем в команду"):
    """Спросить у подставного провайдера жанр присланного поста."""
    return await classify_post_genre(text, provider({CHAT: answer}), "qwen", "Русский")


async def test_a_judged_post_comes_back_with_its_reason():
    """Разобранный ответ отдаёт и жанр, и обоснование."""
    genre, trouble = await _asked(
        chat_json({"is_vacancy": True, "reason": "«Ищем в команду», названы обязанности"})
    )

    assert trouble is None
    assert genre.is_vacancy is True
    assert genre.reason == "«Ищем в команду», названы обязанности"


async def test_a_verdict_without_a_reason_is_not_taken():
    """Вердикт без обоснования не берётся — ни в ту сторону, ни в другую.

    Проверить его нечем: слов, на которые он опирается, нет. По «не вакансия»
    отсюда удаляют строку, а «вакансия» пропускает пост к отправке отклика.
    """
    genre, trouble = await _asked(chat_json({"is_vacancy": False, "reason": None}))

    assert genre is None
    assert trouble is None


async def test_a_verdict_that_is_not_a_yes_or_no_is_not_taken():
    """Жанр, пришедший не признаком, не берётся.

    Модель отвечает и строкой «true», и словом «вакансия». Принять такое
    значило бы зачесть за «вакансия» любое непустое значение — в том числе
    строку «false».
    """
    genre, _trouble = await _asked(
        chat_json({"is_vacancy": "true", "reason": "«Ищем в команду»"})
    )

    assert genre is None


async def test_an_unreadable_answer_is_not_a_trouble():
    """Несуразица в ответе бедой провайдера не считается.

    «Модель ответила, а сказала невнятное» и «спросить не вышло» решают
    разное: по первому пост едет дальше к оценщику, по второму строка ждёт
    следующего захода.
    """
    genre, trouble = await _asked(chat_response("не json вовсе"))

    assert genre is None
    assert trouble is None


async def test_an_empty_post_is_not_asked_about():
    """У пустого текста жанра не спрашивают: спрашивать не о чем."""
    genre, trouble = await classify_post_genre("", provider({}), "qwen", "Русский")

    assert genre is None
    assert trouble is None


async def test_the_reason_is_asked_in_the_user_language():
    """Обоснование читает человек — и пишется на его языке, а не на языке поста."""
    client = provider({CHAT: chat_json({"is_vacancy": True, "reason": "«Ищем в команду»"})})

    await classify_post_genre("Ищем в команду", client, "qwen", "Қазақша")

    assert "язык пользователя: Қазақша" in messages_of(client.sent[0])["system"]
