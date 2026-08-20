"""Верность подделки Telegram настоящему клиенту.

Расхождение подделки с настоящим клиентом опаснее её отсутствия: боевой код
почти везде обёрнут широким `except`, и разошедшийся ответ приходит туда же,
куда пришла бы сетевая ошибка. Проверка после этого зелена при любом исходе, а
сторожит она дорогу, которой в бою не существует.
"""

import pytest
from pyrogram.errors import UsernameNotOccupied

from tests.fakes.telegram import FakeTelegramClient


async def test_the_fake_refuses_a_channel_name_telegram_does_not_know():
    """Подделка бросает на незнакомом имени канала, как настоящий клиент.

    Отдай она `None`, зелёной была бы дорога, которой в бою не существует:
    перехват `UsernameNotOccupied` в `bot/channels` остался бы без сторожа.
    """
    with pytest.raises(UsernameNotOccupied):
        await FakeTelegramClient(chats={}).get_chat("jobs")


async def test_the_fake_refuses_a_username_telegram_does_not_know():
    """Подделка бросает на незанятом имени собеседника — по той же причине.

    Настоящий `get_users` о неизвестном имени не отвечает пустотой, и разбор
    поиска, проверенный на пустоте, в бою проверен не был бы вовсе.
    """
    with pytest.raises(UsernameNotOccupied):
        await FakeTelegramClient(users={}).get_users("user_name")
