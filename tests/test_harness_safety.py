"""Сторож стенда: падает, если подмена не сработала.

Без него неудачная подмена выглядит как зелёный прогон ровно до момента,
когда тесты уйдут в боевую базу или разошлют сообщения живым HR.
"""

import logging

import keyring
import pytest
from sqlalchemy import func, select

from adapters import claude_code
from adapters.lm_chat import ChatRequest, chat
from adapters.lm_studio import make_client
from backend.provider_config import LlmProviderConfig
from adapters.claude import ClaudeClient
from backend.models import Company
from config import get_data_dir, get_database_url
from tests.conftest import TMP_ROOT, EngineReached, ProviderReached, TelegramReached


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


async def test_a_call_into_real_anthropic_blows_up():
    """Обращение к настоящему API Anthropic из теста взрывается.

    SDK ходит своим клиентом `httpx2`, мимо подделок `tests/fakes/llm.py`, и
    без запора тест с забытой подделкой ушёл бы к настоящей модели — за
    деньги, по ключу из окружения.
    """
    client = ClaudeClient(api_key="sk-test", max_retries=0)

    with pytest.raises(ProviderReached, match="настоящего API Anthropic"):
        await client.messages.create(
            model="claude-sonnet-5-5",
            max_tokens=1,
            messages=[{"role": "user", "content": "ping"}],
        )


async def test_running_real_claude_code_blows_up(monkeypatch, tmp_path):
    """Запуск настоящего Claude Code из теста взрывается.

    Каждый такой запуск тратит лимит подписки человека, а тест с забытой
    подделкой запускал бы его молча и проходил бы зелёным.
    """
    # Пути нарочно нет на диске: сними кто-нибудь запор, процесс не запустится
    # вовсе, а не уйдёт к настоящему Claude Code по PATH.
    monkeypatch.setattr(claude_code, "_find_cli", lambda: str(tmp_path / "нет" / "claude.exe"))
    client = make_client(LlmProviderConfig("claude-code", "", "sonnet"))
    request = ChatRequest(purpose="стенд", messages=[{"role": "user", "content": "ping"}], max_tokens=1)

    with pytest.raises(ProviderReached, match="Claude Code"):
        await chat(client, "sonnet", request, logging.getLogger(__name__))


async def test_loading_a_real_embedding_model_blows_up(tmp_path):
    """Загрузка настоящей модели эмбеддингов из теста взрывается.

    Адаптер превращает беды движка в «модель недоступна»; без запора тест с
    забытой подделкой молча грузил бы сотни мегабайт.
    """
    from adapters.gguf_embed import ModelFile

    path = tmp_path / "модель.gguf"
    path.write_bytes(b"GGUF")

    with pytest.raises(EngineReached, match="настоящую модель"):
        await ModelFile(str(path)).embed("текст")


async def test_a_call_into_real_telegram_blows_up():
    """Вызов `Client.invoke` падает, а не уходит на сервер.

    Через него идут обычные запросы клиента, включая те, что
    `backend/bot/` делает мимо `adapters.telegram.send_dm`.
    """
    import pyrogram

    with pytest.raises(TelegramReached, match="настоящего Telegram"):
        await pyrogram.Client.invoke(None, None)


async def test_a_call_through_a_raw_session_blows_up_too():
    """Отправка через отдельную сессию падает так же, а не уходит на сервер.

    Часть работы Pyrogram делает не через клиент, а поднимая отдельную
    сессию: так идут заливка файла, скачивание медиа и подключение. Через
    первый из этих путей отправка файла заливала его на сервера Telegram и
    упиралась в верхний запор только на последнем шаге — файл к тому
    моменту уже был там.
    """
    import pyrogram

    with pytest.raises(TelegramReached, match="настоящего Telegram"):
        await pyrogram.session.Session.send(None, None)


async def test_starting_a_raw_session_blows_up():
    """Подключение сессии падает до того, как откроет сокет.

    `Session.start` соединяется сама и только потом шлёт первый пакет — и шлёт
    его через `send`, мимо `invoke`. Запор на обмене опоздал бы вдвойне:
    соединение к тому мигу уже установлено.
    """
    import pyrogram

    with pytest.raises(TelegramReached, match="настоящего Telegram"):
        await pyrogram.session.Session.start(None)


async def test_creating_an_auth_key_blows_up():
    """Авторизация падает: у неё свой обмен, не через `Session`.

    `Auth.create` открывает соединение сам и зовёт собственный `Auth.invoke`
    другого класса — запоры на клиенте и на сессии её не задевают.
    """
    import pyrogram

    with pytest.raises(TelegramReached, match="настоящего Telegram"):
        await pyrogram.session.Auth.create(None)


async def test_the_telegram_refusal_survives_an_except_exception_block():
    """Запор не проглатывается `except Exception` боевого кода.

    `bot/media.download_media` и `bot/chat` оборачивают вызовы клиента именно так —
    наследник `Exception` дал бы там запись в лог и зелёный прогон.
    """
    import pyrogram

    swallowed = False
    with pytest.raises(TelegramReached):
        try:
            await pyrogram.Client.invoke(None, None)
        except Exception:
            swallowed = True

    assert not swallowed


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
