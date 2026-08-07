"""Сторож стенда: падает, если подмена не сработала.

Без него неудачная подмена выглядит как зелёный прогон ровно до момента,
когда тесты уйдут в боевую базу или разошлют сообщения живым HR.
"""

import keyring
import pytest
from sqlalchemy import func, select

from backend.models import Company
from config import get_data_dir, get_database_url
from tests.conftest import TMP_ROOT


def test_data_dir_is_inside_the_temporary_folder():
    """Каталог данных лежит во временной папке, а не в боевом каталоге."""
    assert get_data_dir().is_relative_to(TMP_ROOT)


def test_database_url_points_at_the_temporary_folder():
    """Строка подключения ведёт во временную папку."""
    assert TMP_ROOT.as_posix() in get_database_url()


def test_a_written_key_lands_in_the_in_memory_store(memory_keyring):
    """Записанный ключ читается обратно и лежит в подставном хранилище, а не в системном."""
    keyring.set_password("jobbot-harness-check", "мастер-ключ", "значение")

    assert keyring.get_password("jobbot-harness-check", "мастер-ключ") == "значение"
    assert memory_keyring.store[("jobbot-harness-check", "мастер-ключ")] == "значение"


async def test_any_call_into_real_telegram_blows_up():
    """Вызов воронки Pyrogram падает, а не уходит на сервер.

    Через `Client.invoke` проходят все запросы клиента, включая те, что
    `backend/bot.py` делает мимо `adapters.telegram.send_dm`.
    """
    import pyrogram

    with pytest.raises(AssertionError, match="настоящего Telegram"):
        await pyrogram.Client.invoke(None, None)


async def test_sending_a_dm_is_locked_during_tests():
    """Отправка заперта: клиент не получает ни одного сообщения."""
    import adapters.telegram

    class Client:
        def __init__(self) -> None:
            self.sent: list[tuple] = []

        async def send_message(self, user, text):
            self.sent.append((user, text))
            raise AssertionError("отправка должна была быть заперта")

    client = Client()
    result = await adapters.telegram.send_dm(client, "@hr", "привет")

    assert result is None
    assert client.sent == []


@pytest.mark.parametrize("run", [1, 2])
async def test_committed_row_does_not_survive_between_runs(session, run):
    """Закоммиченная строка не переживает уборку — двух прогонов подряд это не видно."""
    session.add(Company(name="Изоляция"))
    await session.commit()

    total = await session.scalar(select(func.count()).select_from(Company))
    assert total == 1


@pytest.mark.parametrize("run", [1, 2])
async def test_a_row_committed_through_a_factory_does_not_survive_either(session_factory, run):
    """Строка, закоммиченная своей сессией из фабрики, тоже не переживает уборку."""
    async with session_factory() as writing:
        writing.add(Company(name="Фабрика"))
        await writing.commit()

    async with session_factory() as reading:
        total = await reading.scalar(select(func.count()).select_from(Company))

    assert total == 1
