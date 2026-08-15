"""Стенд моста: поверхность окна поверх настоящей базы, без окна и без канала.

Мост зовётся напрямую питоном — ровно так, как позвало бы окно: домен отвечает
возвратом, и ответа ждут из чужого потока (фикстура `ask`). Ни `QApplication`,
ни `QWebEngineView`, ни `QWebChannel` здесь не создаются: канал переезжает на
pywebview, и тест, знающий про него, переезд бы не пережил.

База настоящая — та же, что у бэкенда. Подделывать её нечем: мост открывает
сессию сам и зовёт модули репозитория по имени.
"""

import asyncio
from concurrent.futures import Future

import pytest

from backend.log_buffer import get_handler
from backend.runtime_settings import RuntimeSettings
from client import window_size
from client.bridge import Api, lifespan
from tests.fakes.ui_bot import UiBot


class LoopRunner:
    """Отправляет корутину в цикл теста вместо своего потока.

    Настоящий `AsyncRunner` держит собственный цикл в своём потоке, а движок
    базы привязан к тому циклу, в котором создан, — фикстура `engine` строит
    его в цикле теста. Чужой поток до него не дотянулся бы, поэтому подмена
    исполняет корутины там же, где живёт движок.

    Ответ отдаётся тем же `concurrent.futures.Future`, что и у настоящего:
    `reply` ждёт от него исход, подъём моста вешает на него обработчик.

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


@pytest.fixture
async def runner() -> LoopRunner:
    """Асинхронная нарочно: цикл спрашивается изнутри него самого."""
    return LoopRunner(asyncio.get_running_loop())


@pytest.fixture
async def runtime_settings(session_factory) -> RuntimeSettings:
    """Пустые настройки: без учётной записи Telegram бот не стартует.

    `lifespan.start` поднимает бота, когда в настройках лежит строка сессии;
    на пустой базе её нет, и подъёма не происходит.
    """
    return await RuntimeSettings.load(session_factory)


@pytest.fixture
async def hub(runtime_settings, session_factory, runner):
    """Хозяйство живого окна — собранное тем же подъёмом, что и в приложении.

    Обработчик журнала возвращается на место после теста: домен «система»
    вешает свой на общий буфер, и без возврата следующий тест писал бы в мост,
    которого уже нет.

    Порождённых работ дожидаемся все, а не только те, чей ответ тест поймал:
    методы попутно кладут вести в очередь и открывают свои сессии уже после
    конца теста — движок к тому мигу закрыт, а соединение остаётся висеть до
    сборщика мусора.

    Гасим из чужого потока, как гасило бы окно: `stop` ждёт мотор, а мотор
    здесь — цикл самого теста, и позванный прямо из него он запер бы себя.
    """
    handler = get_handler()
    previous = handler.on_record
    live = lifespan.start(runner, session_factory, runtime_settings)
    try:
        yield live
    finally:
        await asyncio.to_thread(lifespan.stop, live)
        await runner.drain()
        handler.on_record = previous


@pytest.fixture
async def api(hub) -> Api:
    """Поверхность окна: домены, отвечающие значением."""
    return Api(hub)


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
def with_bot(hub):
    """Ставит подделку бота на место настоящего и отдаёт её же."""

    def _put(**answers) -> UiBot:
        bot = UiBot(**answers)
        hub.bot = bot
        return bot

    return _put


class WindowThatGrows:
    """Окно, которое никуда не едет и всё запоминает.

    Спрашивают его двое — сам рост (`window_size.grow_to_main`) и конец
    мастера, который этот рост зовёт.
    """

    def __init__(self) -> None:
        self.x = 400
        self.y = 300
        self.native = object()
        self.done: list[tuple] = []

    def move(self, x: int, y: int) -> None:
        self.done.append(("переехало", x, y))

    def resize(self, width: int, height: int) -> None:
        self.done.append(("выросло", width, height))


@pytest.fixture
def growing_window(monkeypatch) -> WindowThatGrows:
    """Окно с подменённой рамой: её отпускание только отмечается.

    Настоящее отпускание лезет в форму WinForms, а той нужен рабочий стол.
    """
    fake = WindowThatGrows()
    monkeypatch.setattr(
        window_size,
        "_unlock_frame",
        lambda form: fake.done.append(("рама отпущена",)),
    )
    return fake


class WindowThatPicks:
    """Окно, которое отвечает на диалог выбора файла заранее назначенным.

    Спрашивают его двое — анкета (`cv.pick`) и переписка
    (`hr.pick_media`), — и правило у обеих одно: путь называет человек
    диалогом самого окна, страница до него не дотягивается.
    """

    def __init__(self, chosen) -> None:
        self.chosen = chosen

    def create_file_dialog(self, *args, **kwargs):
        return self.chosen
