"""Следствия, которые наблюдают тесты `backend/telegram_lookup.py`."""

import logging

import pytest
from pyrogram.errors import (
    ChannelInvalid, ChannelPrivate, FloodWait, PeerIdInvalid, UsernameInvalid, UsernameNotOccupied,
)

from backend.domain.telegram_identity import post_address
from backend.telegram_lookup import ask_telegram, fetch_telegram_avatar, read_post, resolve_hr_telegram
from tests.fakes.telegram import FakeTelegramClient, WithMessages
from tests.fakes.telegram_objects import photo, post, user


@pytest.mark.parametrize(("trouble", "said"), [
    (UsernameNotOccupied(), "tg_invalid"),
    (UsernameInvalid(), "tg_invalid"),
    (ChannelPrivate(), "tg_private"),
    (PeerIdInvalid(), "tg_private"),
    (ChannelInvalid(), "tg_private"),
    (FloodWait(value=3), "tg_error"),
    (OSError("сеть"), "tg_error"),
], ids=["нет имени", "негодное имя", "закрыт", "нет пира", "негодный канал", "подождать", "сеть"])
async def test_each_telegram_trouble_has_its_own_word(trouble, said):
    """Человеку беды Telegram говорят разное: опечатку чинят в адресе, закрытый
    канал — подпиской, прочее — повтором."""

    async def asking():
        raise trouble

    assert await ask_telegram("вопрос", asking) == (None, said)


async def test_an_answered_question_has_no_trouble():
    async def asking():
        return "ответ"

    assert await ask_telegram("вопрос", asking) == ("ответ", None)


async def test_a_post_of_a_public_channel_is_read_by_its_nick():
    """Публичный канал читается и без подписки — по нику из ссылки."""
    found = post(5, text="Ищем QA")
    client = WithMessages(post=found)

    assert await read_post(client, post_address("https://t.me/PyJobs/5")) == (found, None)
    assert client.asked == [("pyjobs", 5)]


async def test_a_post_of_a_closed_channel_is_asked_by_its_number():
    """У закрытого канала ника нет: спрашивают номером канала, и числом —
    строкой Pyrogram принял бы его за телефон."""
    client = WithMessages(post=post(5))

    await read_post(client, post_address("https://t.me/c/123/5"))

    assert client.asked == [(-100123, 5)]


@pytest.mark.parametrize("answer", [None, post(5, empty=True)], ids=["пусто", "удалён"])
async def test_a_missing_post_is_no_post(answer):
    client = WithMessages(post=answer)

    assert await read_post(client, post_address("https://t.me/pyjobs/5")) == (None, "no_post")


async def test_a_closed_channel_without_subscription_is_its_own_trouble():
    client = WithMessages(error=ChannelPrivate())

    assert await read_post(client, post_address("https://t.me/c/123/5")) == (None, "tg_private")


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


async def test_a_flood_wait_without_a_number_still_reaches_the_log(caplog):
    """Запрет без названного срока запись в журнале не съедает.

    Срок Telegram называет не всегда. Собери запись числом — на месте срока
    оказалась бы строка, сборка сообщения упала бы, и в журнале не осталось
    бы ничего: ни срока, ни самого запрета.
    """
    client = FakeTelegramClient(fails={"download_media": FloodWait()})
    entity = user(photo=photo(small_file_id="small-1"))

    with caplog.at_level(logging.WARNING, logger="backend.telegram_lookup"):
        assert await fetch_telegram_avatar(client, entity) is None

    assert [
        rec for rec in caplog.records
        if rec.name == "backend.telegram_lookup" and "FloodWait" in rec.getMessage()
    ]


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
    """Неизвестное Telegram имя даёт отсутствие, а не бросок наружу.

    Telegram отвечает на такое отказом, а поиск собеседника идёт попутно: урони
    он зовущего — разбор объявления вставал бы из-за ненайденного ника.
    """
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
