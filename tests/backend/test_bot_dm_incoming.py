"""Следствия входящего сообщения от HR.

Разбор входящего целиком лежит в конвейере; боту здесь принадлежат две вещи:
не пускать разбор при выключенном боте и сказать окну, чью переписку
перерисовать. Второе делается уже после разбора — до него HR может быть ещё
не заведён, и говорить было бы не о ком.
"""

import pytest

from backend.models import BotMode
from tests.fakes.telegram import chat, incoming, message


@pytest.fixture
def dm_reader(monkeypatch):
    """Подменяет разбор входящего: он живёт в конвейере, а не в боте."""
    seen: list = []

    async def process_dm(msg, *args, **kwargs):
        seen.append(msg)

    monkeypatch.setattr("backend.bot.updates.process_dm", process_dm)
    return seen


async def test_an_incoming_message_goes_to_the_pipeline(chatting, dm_reader):
    """Входящее уходит в конвейер на разбор."""
    bot, client, hr = await chatting(telegram_user_id=777)
    msg = incoming()

    await bot._on_dm(client, msg)

    assert dm_reader == [msg]


async def test_a_switched_off_bot_does_not_read_incoming_messages(
    chatting, dm_reader
):
    """Выключенный бот входящие не разбирает.

    «Выключен» означает и это тоже: не читать ответы HR и не менять по
    ним статусы вакансий.
    """
    bot, client, hr = await chatting(mode=BotMode.OFF, telegram_user_id=777)

    await bot._on_dm(client, incoming())

    assert dm_reader == []


async def test_the_window_hears_about_an_incoming_message(chatting, dm_reader):
    """Окно узнаёт о входящем: открытая переписка обновится сразу."""
    bot, client, hr = await chatting(telegram_user_id=777)
    heard: list[int] = []
    bot.on_new_message = heard.append

    await bot._on_dm(client, incoming())

    assert heard == [hr.id]


async def test_a_message_from_a_stranger_does_not_reach_the_window(
    chatting, dm_reader
):
    """О письме незнакомого собеседника окну не сообщают.

    Перерисовывать нечего: переписки с ним во вкладке «Контакты» нет.
    """
    bot, client, hr = await chatting(telegram_user_id=777)
    heard: list[int] = []
    bot.on_new_message = heard.append

    await bot._on_dm(client, incoming(user_id=999))

    assert heard == []


async def test_a_message_without_a_sender_does_not_reach_the_window(
    chatting, dm_reader
):
    """Сообщение без отправителя окну не показывают: чью переписку чинить."""
    bot, client, hr = await chatting(telegram_user_id=777)
    heard: list[int] = []
    bot.on_new_message = heard.append
    msg = message(id=10, text="ниоткуда", chat=chat(id=777), from_user=None)

    await bot._on_dm(client, msg)

    assert dm_reader == [msg]
    assert heard == []


async def test_an_hr_known_only_by_name_is_found_too(chatting, dm_reader):
    """HR, известный только по имени, тоже опознаётся.

    Номер собеседника заводится позже — при первом разборе; до того у
    строки есть одно только имя.
    """
    bot, client, hr = await chatting(telegram_username="maria", telegram_user_id=None)
    heard: list[int] = []
    bot.on_new_message = heard.append

    await bot._on_dm(client, incoming(user_id=999, username="maria"))

    assert heard == [hr.id]


async def test_a_broken_window_hook_does_not_break_the_handler(
    chatting, dm_reader
):
    """Сломанное оповещение окна разбор входящего не отменяет."""
    bot, client, hr = await chatting(telegram_user_id=777)

    def broken(hr_id):
        raise RuntimeError("окно")

    bot.on_new_message = broken
    msg = incoming()

    await bot._on_dm(client, msg)

    assert dm_reader == [msg]
