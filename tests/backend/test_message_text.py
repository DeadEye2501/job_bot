"""Следствия, которые наблюдают тесты `backend/message_text.py`.

Приватный `_media_placeholder` проверяется через `extract_dm_text`: снаружи
он виден только подстановкой в цитату ответа.
"""

from backend.message_text import extract_dm_text, extract_text
from tests.fakes.telegram import message


def test_text_comes_from_the_text_field_trimmed():
    """Текст берётся из поля text без окружающих пробелов."""
    assert extract_text(message(text="  привет  ")) == "привет"


def test_caption_is_used_when_text_is_empty():
    """При пустом тексте берётся подпись."""
    assert extract_text(message(text=None, caption="подпись")) == "подпись"


def test_no_text_and_no_caption_gives_empty_string():
    """Без текста и подписи выходит пустая строка."""
    assert extract_text(message()) == ""


def test_message_without_a_reply_is_returned_as_is():
    """Сообщение без ответа отдаётся как есть."""
    assert extract_dm_text(message(text="тело")) == "тело"


def test_voice_without_text_is_named_in_words():
    """Голосовое без текста называется словами, а не пустым баблом."""
    assert extract_dm_text(message(voice=object())) == "Голосовое сообщение"


def test_voice_with_a_caption_keeps_the_caption():
    """Голосовое с подписью сохраняет подпись."""
    got = extract_dm_text(message(caption="послушай", voice=object()))
    assert got == "Голосовое сообщение: послушай"


def test_a_reply_is_prefixed_with_the_parent_quote():
    """Ответ предваряется цитатой родителя."""
    parent = message(text="вопрос")
    got = extract_dm_text(message(text="ответ", reply_to_message=parent))
    assert got == "↪ вопрос\n\nответ"


def test_a_reply_without_its_own_text_is_just_the_quote():
    """Ответ без своего текста состоит из одной цитаты."""
    parent = message(text="вопрос")
    got = extract_dm_text(message(reply_to_message=parent))
    assert got == "↪ вопрос"


def test_newlines_in_the_quote_collapse_to_spaces():
    """Перевод строки в цитате схлопывается в пробел."""
    parent = message(text="первая\nвторая")
    got = extract_dm_text(message(text="ответ", reply_to_message=parent))
    assert got.startswith("↪ первая вторая\n\n")


def test_a_long_quote_is_cut_and_gets_an_ellipsis():
    """Длинная цитата обрезается и получает многоточие."""
    parent = message(text="я" * 200)
    got = extract_dm_text(message(text="ответ", reply_to_message=parent))
    quote = got.split("\n\n")[0]
    assert quote == "↪ " + "я" * 79 + "…"


def test_a_reply_to_a_photo_quotes_a_placeholder():
    """Ответ на фото цитирует подстановку вместо текста."""
    parent = message(photo=object())
    got = extract_dm_text(message(text="ответ", reply_to_message=parent))
    assert got == "↪ [Фото]\n\nответ"


def test_a_reply_to_a_document_quotes_its_own_placeholder():
    """Ответ на документ цитирует свою подстановку."""
    parent = message(document=object())
    got = extract_dm_text(message(text="ответ", reply_to_message=parent))
    assert got == "↪ [Документ]\n\nответ"
