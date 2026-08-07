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
from tests.fakes.keyring import MemoryKeyring


def test_data_dir_is_inside_the_temporary_folder():
    """Каталог данных лежит во временной папке, а не в боевом каталоге."""
    assert get_data_dir().is_relative_to(TMP_ROOT)


def test_database_url_points_at_the_temporary_folder():
    """Строка подключения ведёт во временную папку."""
    assert TMP_ROOT.as_posix() in get_database_url()


def test_keyring_backend_is_the_in_memory_fake():
    """Хранилище ключей подставное, боевой мастер-ключ недосягаем."""
    assert isinstance(keyring.get_keyring(), MemoryKeyring)


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
async def test_inserted_row_does_not_survive_between_runs(session, run):
    """Вставленная строка не переживает откат — двух прогонов подряд это не видно."""
    session.add(Company(name="Изоляция"))
    await session.flush()

    total = await session.scalar(select(func.count()).select_from(Company))
    assert total == 1
