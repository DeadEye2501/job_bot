"""Фикстуры, общие для тестов слоя `backend`."""

import shutil

import pytest

from backend.bot import MEDIA_DIR, Bot
from backend.models import (
    HR,
    BotMode,
    LlmConfigKind,
    Vacancy,
    VacancyStatus,
)
from backend.repository import list_vacancies
from backend.runtime_settings import RuntimeSettings, encrypt_str
from tests.dbio import only_row, put
from tests.factories import hr_row, llm_config_row, tg_account_row, vacancy_row
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


class Outbox:
    """Ушедшие письма вместо настоящей отправки.

    Подменяет собой `adapters.telegram.send_dm` целиком: до Pyrogram вызов
    не доходит, поэтому запор стенда остаётся нетронутым — снимается только
    признак, по которому боевой код решает, имитировать отправку или нет.
    """

    def __init__(self) -> None:
        self.sent: list[tuple] = []
        self.error: BaseException | None = None
        self.assigned_id = 1000

    async def send_dm(self, _client, target, text, attachment=None):
        if self.error is not None:
            raise self.error
        self.sent.append((target, text, attachment))
        return self.assigned_id


@pytest.fixture(autouse=True)
def empty_media_dir():
    """Пустая папка вложений на каждый тест.

    Файл в ней — состояние, которое проверяют сразу двое: пропуск
    повторного скачивания и копия ушедшего. Остаток от соседнего теста
    подменял бы «положили» на «уже было» и красил проверки зелёным в
    зависимости от порядка запуска.
    """
    if MEDIA_DIR.exists():
        shutil.rmtree(MEDIA_DIR)
    yield
    if MEDIA_DIR.exists():
        shutil.rmtree(MEDIA_DIR)


@pytest.fixture
def chatting(session_factory, make_bot):
    """Бот в заданном режиме, подставной клиент Telegram и сохранённый HR.

    Переписка с HR проверяется тремя слайсами — отметки о прочтении,
    сообщения, файлы, — и каждому нужно одно и то же: режим, в котором бот
    вообще что-то делает, клиент, который запишет обращения, и HR с
    адресом.
    """

    async def build(*, mode=BotMode.FULL, client=None, **hr_fields):
        telegram_client = client if client is not None else FakeTelegramClient()
        await put(session_factory, hr_row(**hr_fields))
        bot = await make_bot(telegram_client)
        await bot._rs.set_mode(mode)
        return bot, telegram_client, await only_row(session_factory, HR)

    return build


@pytest.fixture
def sending_unlocked(monkeypatch):
    """Снимает признак заглушки: боевой код начинает отправлять по-настоящему.

    По умолчанию стенд держит `SEND_LOCKED = True`, и ветки настоящей
    отправки не исполняются вовсе. Снимать признак можно только тем,
    у кого вместо клиента Pyrogram подделка: до сети иначе дойдёт.
    """
    import adapters.telegram

    monkeypatch.setattr(adapters.telegram, "SEND_LOCKED", False)


@pytest.fixture
def outbox(monkeypatch, sending_unlocked):
    """Отправка отклика с подменённым отправителем.

    Подменяется `adapters.telegram.send_dm` целиком, поэтому настоящий
    Pyrogram остаётся недостижим и со снятым признаком заглушки.
    """
    import adapters.telegram

    box = Outbox()
    monkeypatch.setattr(adapters.telegram, "send_dm", box.send_dm)
    return box


@pytest.fixture
def ready_to_send(session_factory, make_bot):
    """Бот в рабочем режиме, HR с адресом и вакансия в заданном статусе.

    Отправка отклика проверяется тремя слайсами — отказы, следы, беды, — и
    каждому нужна одна и та же обстановка: без рабочего режима отправка
    отказывает, без адреса у HR тоже, а без вакансии не с чем сверять
    статус.
    """

    async def build(*, status=VacancyStatus.NEW, mode=BotMode.FULL, hr=None):
        await put(
            session_factory,
            hr if hr is not None else hr_row(),
            vacancy_row(title="к отклику", status=status),
        )
        bot = await make_bot()
        await bot._rs.set_mode(mode)
        saved_hr = await only_row(session_factory, HR)
        vacancy = await only_row(session_factory, Vacancy)
        return bot, saved_hr, vacancy

    return build
