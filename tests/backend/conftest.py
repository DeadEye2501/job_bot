"""Фикстуры, общие для тестов слоя `backend`."""

from backend.flows import apply
from backend.flows import dm_classify
import asyncio
import logging
import shutil
from contextlib import suppress

import pytest

from backend.bot.media import MEDIA_DIR
from backend.bot.client import Bot
from backend.flows.dm import process_dm
from backend.flows.pipeline import IngestionPipeline
from backend.models import (
    HR,
    BotMode,
    LlmConfigKind,
    Profile,
    Vacancy,
    VacancyStatus,
)
from backend.crypto import encrypt_str
from backend.payloads import FitValidation
from backend.repository.vacancies_list import list_vacancies
from backend.runtime_settings import RuntimeSettings
from tests.dbio import only_row, put
from tests.factories import (
    hr_row,
    llm_config_row,
    parsed_vacancy,
    profile_row,
    profile_skill_row,
    tg_account_row,
    vacancy_row,
)
from tests.fakes.telegram import FakeTelegramClient, photo, user


@pytest.fixture
def clean_root_logger():
    """Возвращает корневой logger в исходное состояние после теста.

    Помимо списка обработчиков, фильтров и собственного уровня снимает и
    восстанавливает уровень каждого уже навешенного обработчика: установка
    буфера журнала правит их на месте, и без возврата чужой обработчик —
    например, тот, которым pytest ловит записи, — остался бы испорченным
    до конца прогона.
    """
    root = logging.getLogger()
    handlers = list(root.handlers)
    filters = list(root.filters)
    level = root.level
    handler_levels = {h: h.level for h in handlers}
    yield root
    root.handlers = handlers
    root.filters = filters
    root.setLevel(level)
    for handler, original_level in handler_levels.items():
        handler.setLevel(original_level)


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


class LmClient:
    """Заглушка соединения с языковой моделью: помнит адрес и закрытие."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url
        self.closed = 0

    async def aclose(self) -> None:
        self.closed += 1


@pytest.fixture
def make_bot(session_factory, monkeypatch):
    """Собирает `Bot` на подставном клиенте Telegram и без соединений к LLM.

    Настоящая сборка поднимает клиента Pyrogram и два клиента httpx — на
    каждый тест это и медленно, и заводит на диске файл сессии. Поэтому обе
    сборки подменяются: клиент Telegram становится подделкой, которую тест
    получает обратно, а клиенты LLM — заглушками, которые помнят свой адрес
    и умеют закрываться. По адресу видно, какая досталась чату, а какая
    векторам; по закрытию — что остановка их не забыла.
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
        telegram_client = client if client is not None else FakeTelegramClient()
        monkeypatch.setattr(
            "adapters.telegram.make_client", lambda tg: telegram_client
        )
        monkeypatch.setattr(
            "adapters.lm_studio.make_client", lambda cfg: LmClient(cfg.base_url)
        )
        return Bot(settings, session_factory, dry_run=dry_run)

    return build


@pytest.fixture
async def make_pipeline(session_factory):
    """Собирает `IngestionPipeline` на подделках вместо живых соединений.

    Настоящий конвейер держит клиента Pyrogram и два клиента httpx.
    Отдельно от `make_bot` он нужен потому, что проверяется сам конвейер, а
    не бот вокруг него: собирать ради него бота значило бы тащить в тест
    обработчики, цикл и настройки, к делу не относящиеся.

    Отправка письма подменяется списком: конвейер зовёт её как обычную
    сопрограмму, а тест смотрит, что и кому ушло.
    """
    built: list = []

    async def build(client=None):
        settings = await RuntimeSettings.load(session_factory)
        pipeline = _pipeline_on_fakes(
            session_factory, client or FakeTelegramClient(), settings
        )
        built.append(pipeline)
        return pipeline

    yield build

    await _put_out_backfills(built)


def _pipeline_on_fakes(session_factory, client, settings) -> IngestionPipeline:
    """Конвейер на подделках; отправку письма подменяет список `sent`."""
    outgoing: list[tuple] = []

    async def send(hr, text, attachment=None, vacancy_id=None, *, force=False):
        outgoing.append((hr.id, text, attachment, vacancy_id, force))
        return True

    pipeline = IngestionPipeline(
        client=client,
        session_factory=session_factory,
        lm_client=LmClient("http://provider.test"),
        lm_embed_client=LmClient("http://provider.test"),
        lm_chat_model="qwen",
        lm_embed_model="bge",
        send=send,
        runtime_settings=settings,
    )
    pipeline.sent = outgoing
    return pipeline


async def _put_out_backfills(pipelines) -> None:
    """Гасит фоновые догоны переписки, заведённые за время теста.

    Разбор вакансии заводит их сам при появлении нового HR. Брошенная
    задача жалуется в поток ошибок при сборке мусора, и жалоба всплывает
    посреди чужого прогона.
    """
    for pipeline in pipelines:
        for task in list(pipeline._backfill_tasks):
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


def _known_hr_client() -> FakeTelegramClient:
    """Подделка Telegram, знающая одного HR — с картинкой профиля."""
    return FakeTelegramClient(
        users={
            "maria": user(
                id=777,
                username="maria",
                first_name="Мария",
                photo=photo(small_file_id="кар"),
            )
        },
        avatar=b"\x89PNG",
    )


def _answer_instead_of_the_model(pipeline, monkeypatch) -> None:
    """Подменяет разбор, проверку пригодности и отправку заготовленным."""

    async def parse_vacancy(text, client_, model, **kwargs):
        return pipeline.parsed

    async def validate_vacancy_fit(parsed, text, client_, model, **kwargs):
        pipeline.validated = True
        return pipeline.verdict

    async def try_auto_send(pipeline, hr, parsed, vacancy_id):
        pipeline.asked_to_send.append(vacancy_id)
        return True, "sent"

    monkeypatch.setattr(apply, "_try_auto_send", try_auto_send)
    monkeypatch.setattr("backend.flows.parse.parse_vacancy", parse_vacancy)
    monkeypatch.setattr("backend.flows.parse.validate_vacancy_fit", validate_vacancy_fit)


@pytest.fixture
def deliver(session_factory):
    """Проводит письмо через разбор входящего.

    Нужен двум слайсам — «кого слушают» и «к какой вакансии относят», — и
    оба зовут одно и то же с разными подменами: клиентом Telegram и
    накопителем отложенного разбора.
    """

    async def run(msg, *, client=None, schedule=None):
        await process_dm(
            msg,
            None,
            "qwen",
            session_factory,
            client=client,
            schedule_classification=schedule,
        )

    return run


@pytest.fixture
async def unparsed_vacancy(session_factory):
    """Неразобранная вакансия с чужим приговором.

    Приговор именно чужой: с умолчаниями «осталась новой» проверка была бы
    верна и до разбора, то есть не стерегла бы ничего.
    """
    await put(
        session_factory,
        vacancy_row(
            title=None,
            is_parsed=False,
            raw_text="текст",
            status=VacancyStatus.NOT_FIT,
            skip_reason="прошлый отказ",
        ),
    )
    return await only_row(session_factory, Vacancy)


@pytest.fixture
async def parsing(make_pipeline, monkeypatch, unparsed_vacancy, session_factory):
    """Конвейер с подставным разбором объявления.

    Разбор проверяется двумя слайсами — приговор и запись, — и обоим нужно
    одно: чтобы обращения к языковой модели отдавали заготовленное, а
    оценка по навыкам не отсекала всё на пороге.
    """
    pipeline = await make_pipeline(_known_hr_client())
    pipeline.parsed = parsed_vacancy(
        title="Python-разработчик",
        description="Ищем в команду",
        stack_required=["Python"],
        grade="middle",
        salary="200000",
        remote="remote",
        location="Ереван",
    )
    pipeline.verdict = FitValidation(verdict="fit", reason=None)
    pipeline.validated = False
    pipeline.asked_to_send = []
    _answer_instead_of_the_model(pipeline, monkeypatch)

    await put(session_factory, profile_row())
    profile = await only_row(session_factory, Profile)
    await put(session_factory, profile_skill_row(profile.id, "Python"))
    await pipeline._reload_resources()
    await pipeline._rs.set_app("scoring_threshold", "1")
    return pipeline, unparsed_vacancy


@pytest.fixture
async def dm_pipeline(monkeypatch, make_pipeline):
    """Конвейер с подставным разбором ответа HR и невзводящимся таймером.

    Накопитель входящих проверяется двумя слайсами — что в нём копится и
    что с ним делает остановка, — и обоим нужно одно: чтобы разбор не
    уходил в языковую модель и не срабатывал сам по себе. Тест, которому
    нужно срабатывание, ставит своё ожидание.
    """
    built = await make_pipeline()
    built.DM_CLASSIFY_DEBOUNCE_SEC = 30
    built.classified = []

    async def classify(pipeline, hr_id):
        built.classified.append(
            (hr_id, list(built._dm_classify_buffer.get(hr_id, [])))
        )
        built._dm_classify_buffer.pop(hr_id, None)

    monkeypatch.setattr(dm_classify, "_classify_and_apply_for_hr", classify)
    yield built
    await built.cancel_pending_dm_classifications()


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
