"""Следствия добавления канала из окна настроек.

Существование канала проверяется у Telegram до записи в базу: опечатка иначе
завела бы строку без названия и картинки, которую пользователь потом ищет
глазами среди живых. Тем же вызовом забираются название и аватар — второго
обращения ради них не делается.

Повтор ищется дважды, до обращения и после: пока идёт вопрос к Telegram,
строку может успеть вставить соседнее окно.
"""

import logging

from backend.models import TelegramChannel
from tests.dbio import all_rows, only_row, put
from tests.factories import channel_row
from tests.fakes.telegram import FakeTelegramClient, chat, photo


async def test_a_known_channel_is_returned_instead_of_added_again(
    make_bot, session_factory
):
    """Уже добавленный канал возвращается, а не заводится вторым.

    Telegram при этом не спрашивают: строка есть, а обращение стоит
    ожидания в окне.
    """
    await put(session_factory, channel_row(username="jobs"))
    known = await only_row(session_factory, TelegramChannel)
    client = FakeTelegramClient()
    bot = await make_bot(client)

    assert await bot.add_channel("jobs") == (known.id, "exists")
    assert client.get_chat_calls == []


async def test_a_channel_unknown_to_telegram_is_not_written_down(
    make_bot, session_factory
):
    """Неизвестный Telegram канал в базу не попадает.

    Иначе опечатка заводила бы строку без названия и картинки — отличить
    её от живого канала пользователь смог бы только глазами.
    """
    bot = await make_bot(FakeTelegramClient(chats={}))

    assert await bot.add_channel("опечатка") == (None, "invalid")
    assert await all_rows(session_factory, TelegramChannel) == []


async def test_a_telegram_failure_is_not_written_down_either(
    make_bot, session_factory
):
    """Сбой обращения к Telegram строку не заводит и «нет канала» не называет.

    Строка без названия хуже повторной попытки, но и сказать про опечатку
    здесь нельзя: имя может быть верным, а отвалиться — сеть. Человек, которому
    сказали «проверьте имя», перебирал бы верное написание.
    """
    bot = await make_bot(FakeTelegramClient(fails={"get_chat": OSError("сеть")}))

    assert await bot.add_channel("jobs") == (None, "error")
    assert await all_rows(session_factory, TelegramChannel) == []


async def test_a_name_telegram_does_not_know_is_called_by_its_own_word(
    make_bot, session_factory
):
    """Незанятое имя называется своим отказом, а не общей бедой.

    Так окно скажет «проверьте имя» ровно там, где имя и виновато: Telegram
    отвечает на такое отдельным родом отказа.
    """
    from pyrogram.errors import UsernameNotOccupied

    bot = await make_bot(
        FakeTelegramClient(fails={"get_chat": UsernameNotOccupied()})
    )

    assert await bot.add_channel("опечатка") == (None, "invalid")
    assert await all_rows(session_factory, TelegramChannel) == []


async def test_a_telegram_failure_leaves_its_trace_in_the_log(make_bot, caplog):
    """Отказ Telegram оставляет в журнале трассировку, а не только род и текст.

    Причина отказа тут одна на всех — «invalid», — и по ней потом не отличить
    опечатку в имени от оборванной сети. Разбирать это можно только по журналу.
    """
    bot = await make_bot(FakeTelegramClient(fails={"get_chat": OSError("сеть")}))

    with caplog.at_level(logging.WARNING):
        await bot.add_channel("jobs")

    assert "Traceback (most recent call last)" in caplog.text
    assert "OSError: сеть" in caplog.text


async def test_a_new_channel_keeps_the_title_telegram_gave(
    make_bot, session_factory
):
    """Новый канал сохраняется с названием, полученным от Telegram."""
    bot = await make_bot(FakeTelegramClient(chats={"jobs": chat(title="Работа")}))

    channel_id, status = await bot.add_channel("jobs")

    assert status == "created"
    saved = await only_row(session_factory, TelegramChannel)
    assert saved.id == channel_id
    assert saved.title == "Работа"
    assert saved.is_active is True


async def test_a_username_is_stored_in_lower_case(make_bot, session_factory):
    """Имя канала сохраняется строчными.

    Telegram к регистру безразличен, а база нет: «JobsHere» и «jobshere»
    иначе стали бы двумя строками об одном канале.
    """
    bot = await make_bot(FakeTelegramClient(chats={"JobsHere": chat(title="Р")}))

    await bot.add_channel("JobsHere")

    saved = await only_row(session_factory, TelegramChannel)
    assert saved.username == "jobshere"


async def test_an_avatar_is_fetched_when_the_channel_has_one(
    make_bot, session_factory
):
    """Аватар подгружается тем же обращением, если он у канала есть."""
    client = FakeTelegramClient(
        chats={"jobs": chat(title="Работа", photo=photo(big_file_id="кар"))},
        avatar=b"\x89PNG",
    )
    bot = await make_bot(client)

    await bot.add_channel("jobs")

    saved = await only_row(session_factory, TelegramChannel)
    assert saved.avatar == b"\x89PNG"
    assert client.download_calls == ["кар"]


async def test_a_channel_without_a_picture_is_not_asked_for_one(
    make_bot, session_factory
):
    """У канала без картинки её не запрашивают: скачивать нечего."""
    client = FakeTelegramClient(chats={"jobs": chat(title="Работа")}, avatar=b"\x89PNG")
    bot = await make_bot(client)

    await bot.add_channel("jobs")

    saved = await only_row(session_factory, TelegramChannel)
    assert saved.avatar is None
    assert client.download_calls == []


async def test_a_channel_added_meanwhile_is_returned_not_duplicated(
    make_bot, session_factory
):
    """Строка, вставленная соседним окном за время вопроса, не удваивается.

    Проверка повтора идёт дважды нарочно: между первой и обращением к
    Telegram проходит сетевое ожидание, за которое соседнее окно успевает
    вставить ту же строку.
    """

    class SlowClient(FakeTelegramClient):
        """Пока идёт вопрос к Telegram, строку вставляет кто-то другой."""

        async def get_chat(self, chat_id):
            await put(session_factory, channel_row(username="jobs", title="Чужая"))
            return await super().get_chat(chat_id)

    bot = await make_bot(SlowClient(chats={"jobs": chat(title="Своя")}))

    channel_id, status = await bot.add_channel("jobs")

    assert status == "exists"
    saved = await only_row(session_factory, TelegramChannel)
    assert saved.id == channel_id
    assert saved.title == "Чужая"
