"""Стенд моста: поверхность окна поверх настоящей базы, без окна и без канала.

Мост зовётся напрямую питоном — ровно так, как позвало бы окно. Ответ ловится
двояко, пока поверхностей две: у переехавших доменов он возвращается зовущему
(фикстура `ask`, зов из чужого потока), у непереехавших приезжает сигналом
(ловушка `Caught`). Ни `QApplication`, ни `QWebEngineView`, ни `QWebChannel`
здесь не создаются: канал переезжает на pywebview, и тест, знающий про него,
переезд бы не пережил.

База настоящая — та же, что у бэкенда. Подделывать её нечем: мост открывает
сессию сам и зовёт шестнадцать модулей репозитория по имени.
"""

import asyncio
import json
from concurrent.futures import Future

import pytest
from PySide6.QtWidgets import QFileDialog

from backend.log_buffer import get_handler
from backend.runtime_settings import RuntimeSettings
from client.bridge import MainApi, WizardApi
from client.bridge.api import Api
from tests.fakes.ui_bot import UiBot


class LoopRunner:
    """Отправляет корутину в цикл теста вместо своего потока.

    Настоящий `AsyncRunner` держит собственный цикл в своём потоке, а движок
    базы привязан к тому циклу, в котором создан, — фикстура `engine` строит
    его в цикле теста. Чужой поток до него не дотянулся бы, поэтому подмена
    исполняет корутины там же, где живёт движок.

    Ответ отдаётся тем же `concurrent.futures.Future`, что и у настоящего:
    `reply` ждёт от него исход, `_dispatch_json` вешает на него обработчик.

    Отправка идёт через `run_coroutine_threadsafe`, как у настоящего, и по той
    же причине: `reply` зовут из чужого потока, а завести задачу в цикле оттуда
    иначе нельзя.
    """

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop
        self.tasks: list[Future] = []

    def submit(self, coro) -> Future:
        answer = asyncio.run_coroutine_threadsafe(coro, self.loop)
        self.tasks.append(answer)
        return answer

    async def drain(self) -> None:
        """Дожидается всех порождённых работ, включая заведённые по дороге.

        Ждём в цикле, а не одним снимком списка: работа порождает следующую,
        и заведённая уже во время ожидания в снимок не попала бы.
        """
        while self.tasks:
            started, self.tasks = self.tasks, []
            await asyncio.gather(
                *(asyncio.wrap_future(one) for one in started),
                return_exceptions=True,
            )


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
    """
    handler = get_handler()
    previous = handler.on_record
    api = MainApi(runtime_settings, session_factory, runner)
    try:
        yield api
    finally:
        api.cleanup()
        await runner.drain()
        handler.on_record = previous


@pytest.fixture
def watch():
    """Ловушка сигнала непереехавшего домена: `watch(main_api.profile_changed)`."""
    return Caught


@pytest.fixture
async def api(main_api) -> Api:
    """Переехавшая поверхность: домены, отвечающие значением.

    Хозяйство у неё общее со старой — то же, что у живого окна: бот один, и
    подделка, поставленная фикстурой `with_bot`, видна обеим. За порождёнными
    работами прибирает та же фикстура, что и за старой поверхностью.
    """
    return Api(main_api._hub)


@pytest.fixture
def ask():
    """Зов моста из чужого потока: `await ask(api.stats.kpi, "week")`.

    Метод домена ждёт ответа с мотора, и позванный прямо из цикла теста он
    запер бы этот цикл — работа, которой он ждёт, идёт в нём же. pywebview
    зовёт его так же со стороны: из своего потока, а не из мотора.
    """

    async def _ask(method, *args):
        return await asyncio.to_thread(method, *args)

    return _ask


@pytest.fixture
async def wizard_api(runtime_settings, session_factory, runner) -> WizardApi:
    """Поверхность окна первого запуска.

    Ни таймеров, ни бота у мастера нет — прибирать за ним нечего, но работы он
    порождает тем же способом, и дождаться их надо так же.
    """
    api = WizardApi(runtime_settings, session_factory, runner)
    yield api
    await runner.drain()


@pytest.fixture
def chosen_file(monkeypatch):
    """Отвечает за человека в диалоге выбора файла.

    Диалог — статический вызов Qt, поднимающий настоящее окно; подменяется он
    целиком, иначе прогон встал бы на первом же тесте, ожидая нажатия.
    """

    def _choose(path: str) -> None:
        monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (path, ""))

    return _choose


@pytest.fixture
def with_bot(main_api):
    """Ставит подделку бота на место настоящего и отдаёт её же."""

    def _put(**answers) -> UiBot:
        bot = UiBot(**answers)
        main_api._bot = bot
        return bot

    return _put
