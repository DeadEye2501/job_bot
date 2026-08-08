"""Фикстуры, общие для тестов слоя `backend`."""

import pytest

from backend.bot import Bot
from backend.models import LlmConfigKind
from backend.repository import list_vacancies
from backend.runtime_settings import RuntimeSettings, encrypt_str
from tests.dbio import put
from tests.factories import llm_config_row, tg_account_row
from tests.fakes.telegram import FakeTelegramClient


@pytest.fixture
def titles(session):
    """Заголовки отобранных `list_vacancies` вакансий в порядке выдачи.

    Список вакансий проверяется тремя слайсами — отбор, порядок, зарплата, —
    и каждый смотрит на одно и то же: какие строки вернулись и в каком
    порядке. Заголовок здесь опознавательный знак строки, а не предмет
    проверки, поэтому тесты задают его словами, называющими причину, по
    которой строка должна попасть в ответ или не попасть.
    """

    async def read(**kwargs) -> list[str]:
        return [v.title for v in await list_vacancies(session, **kwargs)]

    return read


@pytest.fixture
def make_bot(session_factory, monkeypatch):
    """Собирает `Bot` на подставном клиенте Telegram и без соединений к LLM.

    Настоящая сборка поднимает клиента Pyrogram и два клиента httpx — на
    каждый тест это и медленно, и заводит на диске файл сессии. Поэтому обе
    сборки подменяются: клиент Telegram становится подделкой, которую тест
    получает обратно, а клиенты LLM — метками, по которым видно, какая
    досталась чату, а какая векторам.
    """

    async def build(client=None, *, embed_url="http://provider.test") -> Bot:
        await put(
            session_factory,
            tg_account_row(api_hash_encrypted=encrypt_str("шифр")),
            llm_config_row(LlmConfigKind.CHAT),
            llm_config_row(LlmConfigKind.EMBED, base_url=embed_url),
        )
        settings = await RuntimeSettings.load(session_factory)
        telegram_client = client if client is not None else FakeTelegramClient()
        monkeypatch.setattr(
            "adapters.telegram.make_client", lambda tg: telegram_client
        )
        monkeypatch.setattr(
            "adapters.lm_studio.make_client", lambda cfg: f"клиент {cfg.base_url}"
        )
        return Bot(settings, session_factory)

    return build
