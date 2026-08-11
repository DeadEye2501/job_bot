"""Следствия, которые наблюдают тесты `backend/helpers.py`.

Приватный `_media_placeholder` проверяется через `extract_dm_text`: снаружи
он виден только подстановкой в цитату ответа.
"""

import logging

import pytest
from pyrogram.errors import FloodWait

from backend.helpers import (
    extract_dm_text,
    extract_text,
    fetch_telegram_avatar,
    normalize_username,
    resolve_hr_telegram,
    typed_username,
)
from tests.fakes.telegram import FakeTelegramClient, message, photo, user


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


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("@user_name", "user_name"),
        ("user_name", "user_name"),
        ("https://t.me/user_name", "user_name"),
        ("http://t.me/user_name", "user_name"),
        ("t.me/user_name/", "user_name"),
        ("t.me/user_name/123", "user_name"),
        ("  @user_name  ", "user_name"),
    ],
)
def test_the_username_is_extracted_from_any_link_form(raw, expected):
    """Имя вытаскивается из любой записи ссылки."""
    assert normalize_username(raw) == expected


@pytest.mark.parametrize("typed", ["abcd", "@drew", "t.me/drew"])
def test_a_four_letter_handle_typed_by_a_person_is_accepted(typed):
    """Четырёхбуквенный ник, набранный человеком, принимается.

    Новым такие Telegram не выдаёт, но выданные когда-то работают, и
    собеседник с таким ником — обычное дело. Отвергнув его, форма не дала
    бы завести такого HR вовсе.
    """
    assert typed_username(typed) == typed.rsplit("/", 1)[-1].lstrip("@")


def test_a_four_letter_word_from_an_ad_is_not_taken_for_a_handle():
    """Короткое слово из объявления ником не считается.

    В объявлении контакт пишут как придётся, и «Anna» там — имя, а не ник.
    Приняв его за ник, разбор разыскал бы у Telegram живую чужую учётную
    запись, привязал бы к ней HR — и автоотправка ушла бы постороннему.
    Подтверждать тут некому: за формой стоит человек, за объявлением нет.
    """
    assert normalize_username("Anna") is None


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "",
        "   ",
        "+79991234567",
        "t.me/joinchat/AAAA",
        "t.me/c/12345",
        "abc",
        "1user_name",
        "user-name",
    ],
)
def test_an_unusable_contact_yields_no_username(raw):
    """Негодная запись даёт отсутствие имени, а не мусор."""
    assert normalize_username(raw) is None


async def test_the_avatar_is_downloaded_by_the_small_file_id():
    """Аватар скачивается по малому идентификатору."""
    client = FakeTelegramClient(avatar=b"\x89PNG")
    entity = user(photo=photo(small_file_id="small-1", big_file_id="big-1"))

    assert await fetch_telegram_avatar(client, entity) == b"\x89PNG"
    assert client.download_calls == ["small-1"]


async def test_the_big_file_id_is_used_when_the_small_one_is_absent():
    """Без малого идентификатора берётся большой."""
    client = FakeTelegramClient(avatar=b"data")
    entity = user(photo=photo(big_file_id="big-1"))

    await fetch_telegram_avatar(client, entity)

    assert client.download_calls == ["big-1"]


async def test_an_entity_without_a_photo_has_no_avatar():
    """У собеседника без фотографии аватара нет, и скачивания не было."""
    client = FakeTelegramClient(avatar=b"data")

    assert await fetch_telegram_avatar(client, user()) is None
    assert client.download_calls == []


async def test_a_flood_wait_yields_no_avatar_and_does_not_raise():
    """Ожидание после флуда не даёт аватара и не роняет вызывающего."""
    client = FakeTelegramClient(fails={"download_media": FloodWait(value=42)})
    entity = user(photo=photo(small_file_id="small-1"))

    assert await fetch_telegram_avatar(client, entity) is None


async def test_a_failed_download_leaves_its_trace_in_the_log(caplog):
    """Сорванное скачивание аватара оставляет в журнале трассировку.

    Наружу отказ выглядит как «аватара нет» — тем же самым, чем выглядит
    собеседник без фотографии. Различить их можно только по журналу.
    """
    client = FakeTelegramClient(fails={"download_media": OSError("сеть")})
    entity = user(photo=photo(small_file_id="small-1"))

    with caplog.at_level(logging.WARNING):
        await fetch_telegram_avatar(client, entity)

    assert "Traceback (most recent call last)" in caplog.text
    assert "OSError: сеть" in caplog.text


async def test_an_empty_download_yields_no_avatar():
    """Пустой ответ на скачивание даёт отсутствие аватара."""
    client = FakeTelegramClient(avatar=None)
    entity = user(photo=photo(small_file_id="small-1"))

    assert await fetch_telegram_avatar(client, entity) is None


async def test_an_unusable_contact_never_reaches_telegram():
    """Негодный контакт не доходит до Telegram: сети не касаемся."""
    client = FakeTelegramClient()

    assert await resolve_hr_telegram(client, "+79991234567") is None
    assert client.get_users_calls == []


async def test_a_usable_contact_resolves_to_the_user():
    """Годный контакт отдаёт собеседника, спрошено нормализованное имя."""
    found = user()
    client = FakeTelegramClient(users={"user_name": found})

    assert await resolve_hr_telegram(client, "https://t.me/user_name") is found
    assert client.get_users_calls == ["user_name"]


async def test_a_bot_is_not_accepted_as_an_hr():
    """Бот собеседником не считается."""
    client = FakeTelegramClient(users={"user_name": user(is_bot=True)})

    assert await resolve_hr_telegram(client, "@user_name") is None


async def test_a_deleted_account_is_not_accepted():
    """Удалённый собеседник не считается."""
    client = FakeTelegramClient(users={"user_name": user(is_deleted=True)})

    assert await resolve_hr_telegram(client, "@user_name") is None


async def test_an_unknown_username_resolves_to_nothing():
    """Неизвестное Telegram имя даёт отсутствие."""
    client = FakeTelegramClient(users={})

    assert await resolve_hr_telegram(client, "@user_name") is None


async def test_a_flood_wait_while_resolving_does_not_raise():
    """Ожидание после флуда при поиске не роняет вызывающего."""
    client = FakeTelegramClient(fails={"get_users": FloodWait(value=42)})

    assert await resolve_hr_telegram(client, "@user_name") is None


async def test_a_failed_lookup_leaves_its_trace_in_the_log(caplog):
    """Сорванный поиск собеседника оставляет в журнале трассировку.

    Ответ у отказа тот же, что у неизвестного имени, — отсутствие. HR при
    этом остаётся без адреса, и письмо ему потом не уходит вовсе.
    """
    client = FakeTelegramClient(fails={"get_users": OSError("сеть")})

    with caplog.at_level(logging.WARNING):
        await resolve_hr_telegram(client, "@user_name")

    assert "Traceback (most recent call last)" in caplog.text
    assert "OSError: сеть" in caplog.text
