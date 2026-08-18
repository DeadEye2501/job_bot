"""Обстановка для проверок бота: всё собрано на подделках, до сети не доходит."""

import asyncio
import shutil
from contextlib import suppress

import pytest

from backend.bot.client import Bot
from backend.bot.media import MEDIA_DIR
from backend.crypto import encrypt_str
from backend.models import (
    HR,
    BotMode,
    LlmConfigKind,
    Vacancy,
    VacancyStatus,
)
from backend.runtime_settings import RuntimeSettings
from tests.dbio import only_row, put
from tests.factories import (
    hr_row,
    llm_config_row,
    message_row,
    tg_account_row,
    vacancy_row,
)
from tests.fakes.lm_studio import LmClient
from tests.fakes.telegram import FakeTelegramClient


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


def row_saved_mid_send(session_factory, hr_id):
    """Встречный обработчик исходящих, успевающий записать строку до ответа.

    Гонка проверяется дважды — на сообщении и на файле, — и обеим проверкам
    нужен один и тот же встречный: строка о том же сообщении, положенная в
    базу раньше, чем отправка успела вернуться.
    """

    async def save(answer) -> None:
        await put(
            session_factory,
            message_row(
                hr_id=hr_id,
                is_incoming=False,
                tg_message_id=answer.id,
                text="сохранено обработчиком",
            ),
        )

    return save


@pytest.fixture
def make_bot(session_factory, monkeypatch):
    """Собирает `Bot` на подставном клиенте Telegram и без соединений к LLM.

    Настоящая сборка поднимает клиента Pyrogram и два клиента httpx — на
    каждый тест это и медленно, и заводит на диске файл сессии. Поэтому обе
    сборки подменяются: клиент Telegram становится подделкой, которую тест
    получает обратно, а клиенты LLM — заглушками, которые помнят свой адрес
    и умеют закрываться. По адресу видно, какая досталась чату, а какая
    векторам; по закрытию — что остановка их не забыла.

    Симуляция отправки включается прямо здесь, записью в настройки. Стенд
    заперт двумя слоями (`tests/conftest.py`), и второй из них — `SEND_LOCKED` —
    подъём бота переписывает из этой настройки: в боевом умолчании симуляция
    снята, и без записи подъём снимал бы запор с каждого поднятого бота.
    """

    async def build(
        client=None, *, embed_url="http://provider.test", dry_run=False
    ) -> Bot:
        await put(
            session_factory,
            tg_account_row(api_hash_encrypted=encrypt_str("шифр")),
            llm_config_row(LlmConfigKind.CHAT),
            llm_config_row(LlmConfigKind.EMBED, base_url=embed_url),
        )
        settings = await RuntimeSettings.load(session_factory)
        await settings.set_app("send_locked", "true")
        telegram_client = client if client is not None else FakeTelegramClient()
        monkeypatch.setattr(
            "adapters.telegram.make_client", lambda tg: telegram_client
        )
        monkeypatch.setattr(
            "adapters.lm_studio.make_client", lambda cfg: LmClient(cfg.base_url)
        )
        return Bot(settings, session_factory, dry_run=dry_run)

    return build


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

    async def build(*, mode=BotMode.FULL, client=None, dry_run=False, **hr_fields):
        telegram_client = client if client is not None else FakeTelegramClient()
        await put(session_factory, hr_row(**hr_fields))
        bot = await make_bot(telegram_client, dry_run=dry_run)
        await bot._rs.set_mode(mode)
        return bot, telegram_client, await only_row(session_factory, HR)

    return build


@pytest.fixture
async def busy_slot():
    """Занимает место прогона задачей, которая сама не кончится.

    Задача гасится после теста и досматривается до отмены: брошенная
    жалуется в поток ошибок при сборке мусора, и жалоба всплывает посреди
    чужого прогона.
    """
    occupied: list[asyncio.Task] = []

    def occupy(bot) -> None:
        task = asyncio.create_task(asyncio.sleep(30))
        bot._current_poll_task = task
        occupied.append(task)

    yield occupy

    for task in occupied:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


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

    async def build(
        *, status=VacancyStatus.NEW, mode=BotMode.FULL, hr=None, dry_run=False
    ):
        await put(
            session_factory,
            hr if hr is not None else hr_row(),
            vacancy_row(title="к отклику", status=status),
        )
        bot = await make_bot(dry_run=dry_run)
        await bot._rs.set_mode(mode)
        saved_hr = await only_row(session_factory, HR)
        vacancy = await only_row(session_factory, Vacancy)
        return bot, saved_hr, vacancy

    return build
