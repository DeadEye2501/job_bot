"""Стенд моста: поверхность окна поверх настоящей базы, без окна и без канала.

Мост зовётся напрямую питоном, а ответ ловится подпиской на сигнал — ровно то,
что увидело бы окно. Ни `QApplication`, ни `QWebEngineView`, ни `QWebChannel`
здесь не создаются: канал переезжает на pywebview, и тест, знающий про него,
переезд бы не пережил.

База настоящая — та же, что у бэкенда. Подделывать её нечем: мост открывает
сессию сам и зовёт шестнадцать модулей репозитория по имени.
"""

import asyncio
import json
from concurrent.futures import Future

import pytest

from backend.log_buffer import get_handler
from backend.runtime_settings import RuntimeSettings
from client.bridge import MainApi
from tests.fakes.ui_bot import UiBot


class LoopRunner:
    """Отправляет корутину в цикл теста вместо своего потока.

    Настоящий `AsyncRunner` держит собственный цикл в своём потоке, а движок
    базы привязан к тому циклу, в котором создан, — фикстура `engine` строит
    его в цикле теста. Чужой поток до него не дотянулся бы, поэтому подмена
    исполняет корутины там же, где живёт движок.

    Ответ отдаётся тем же `concurrent.futures.Future`, что и у настоящего:
    `_dispatch_json` вешает на него обработчик и ждёт от него исход.
    """

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop
        self.tasks: list[asyncio.Task] = []

    def submit(self, coro) -> Future:
        answer: Future = Future()
        task = self.loop.create_task(coro)
        self.tasks.append(task)

        def _finish(done: asyncio.Task) -> None:
            if done.cancelled():
                answer.set_exception(asyncio.CancelledError())
                return
            error = done.exception()
            if error is not None:
                answer.set_exception(error)
            else:
                answer.set_result(done.result())

        task.add_done_callback(_finish)
        return answer


class Caught:
    """Копит нагрузку одного сигнала и ждёт следующую.

    Подписка ставится в конструкторе, до вызова слота: мост отвечает сигналом,
    и подписка после вызова потеряла бы уже отправленный ответ.
    """

    def __init__(self, signal) -> None:
        self._payloads: list[str] = []
        self._arrived = asyncio.Event()
        signal.connect(self._remember)

    def _remember(self, payload: str = "") -> None:
        self._payloads.append(payload)
        self._arrived.set()

    async def next(self, timeout: float = 5.0) -> dict:
        """Ждёт ответ и разбирает его как JSON."""
        if not self._payloads:
            await asyncio.wait_for(self._arrived.wait(), timeout)
        self._arrived.clear()
        return json.loads(self._payloads.pop(0))

    async def silent(self, grace: float = 0.05) -> bool:
        """Ответа не было и за отведённое время не появилось."""
        try:
            await asyncio.wait_for(self._arrived.wait(), grace)
        except TimeoutError:
            return True
        return False


@pytest.fixture
async def runner() -> LoopRunner:
    """Асинхронная нарочно: цикл спрашивается изнутри него самого."""
    return LoopRunner(asyncio.get_running_loop())


@pytest.fixture
async def runtime_settings(session_factory) -> RuntimeSettings:
    """Пустые настройки: без учётной записи Telegram бот не стартует.

    `MainApi.__init__` поднимает бота, когда в настройках лежит строка сессии;
    на пустой базе её нет, и подъёма не происходит.
    """
    return await RuntimeSettings.load(session_factory)


@pytest.fixture
async def main_api(runtime_settings, session_factory, runner) -> MainApi:
    """Поверхность основного окна.

    Обработчик журнала возвращается на место после теста: `__init__` вешает
    свой на общий буфер, и без возврата следующий тест писал бы в мост,
    которого уже нет.

    Порождённых работ дожидаемся все, а не только те, чей ответ тест поймал:
    слоты попутно обновляют счётчик непрочитанного, и такая работа открывает
    свою сессию уже после конца теста — движок к тому мигу закрыт, а
    соединение остаётся висеть до сборщика мусора.

    Ждём в цикле, а не одним снимком списка: работа порождает следующую, и
    заведённая уже во время ожидания в снимок не попала бы.
    """
    handler = get_handler()
    previous = handler.on_record
    api = MainApi(runtime_settings, session_factory, runner)
    try:
        yield api
    finally:
        api.cleanup()
        while runner.tasks:
            started, runner.tasks = runner.tasks, []
            await asyncio.gather(*started, return_exceptions=True)
        handler.on_record = previous


@pytest.fixture
def watch():
    """Ловушка сигнала: `watch(api.vacancies_changed)`."""
    return Caught


@pytest.fixture
def with_bot(main_api):
    """Ставит подделку бота на место настоящего и отдаёт её же."""

    def _put(**answers) -> UiBot:
        bot = UiBot(**answers)
        main_api._bot = bot
        return bot

    return _put
