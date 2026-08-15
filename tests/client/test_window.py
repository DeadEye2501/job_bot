"""Следствия открытия и закрытия окна: что приложение делает вокруг него.

Самого окна здесь нет — его поднимает pywebview, а тому нужен настоящий рабочий
стол. Подменён он целиком: предмет тут не окно, а порядок вокруг него, и
ломается этот порядок молча.

Замеры того, чего подменой не проверить — параллельны ли зовы моста, переживает
ли ждущий зов закрытие окна, — сняты руками на живом pywebview и записаны в
плане, слайс А3.
"""

from concurrent.futures import Future

import pytest

from backend.models import BotMode
from client import window as window_module


class FakeWebview:
    """pywebview, который ничего не поднимает и всё запоминает."""

    def __init__(self) -> None:
        self.created: dict = {}

    def create_window(self, title: str, url=None, **options):
        self.created = {"title": title, "url": url, **options}
        return object()

    def start(self, **options) -> None:
        self.started = options


class StubRunner:
    """Мотор, который не заводит ни потока, ни цикла.

    Работу, отправленную до открытия окна, он не исполняет вовсе: единственная
    такая работа — `prepare`, и её следствия сторожатся отдельно, прямо.
    """

    def __init__(self, answer) -> None:
        self.answer = answer
        self.stopped: list[str] = []

    def submit(self, coro) -> Future:
        coro.close()
        done: Future = Future()
        done.set_result(self.answer)
        return done

    def stop(self) -> None:
        self.stopped.append("мотор")


class StubHub:
    """Хозяйство без хозяйства: у гашения оно спрашивает только движок."""

    engine = None


@pytest.fixture
def opened(monkeypatch, runtime_settings, session_factory):
    """Окно, открытое без окна: подменены и pywebview, и мотор, и база."""
    fake = FakeWebview()
    order: list[str] = []
    runner = StubRunner(runtime_settings)

    class StubListener:
        def close(self) -> None:
            order.append("слушатель")

    monkeypatch.setattr(window_module, "webview", fake)
    monkeypatch.setattr(window_module, "_open_runner", lambda: runner)
    monkeypatch.setattr(
        window_module, "_open_database", lambda: (None, session_factory)
    )
    monkeypatch.setattr(
        window_module.raise_window, "listen", lambda window: StubListener()
    )
    monkeypatch.setattr(window_module.lifespan, "start", lambda *a, **k: StubHub())
    monkeypatch.setattr(
        window_module.lifespan, "stop", lambda hub: order.append("мост")
    )
    monkeypatch.setattr(runner, "stop", lambda: order.append("мотор"))
    return fake, order


async def test_the_bot_starts_switched_off_however_it_was_left(
    runtime_settings, session_factory
):
    """Запуск застаёт бота выключенным, каким бы его ни оставили вчера.

    Режим лежит в настройках и переживает выход. Не сбрось его запуск, бот
    принялся бы за работу сам, ещё до того как человек увидел окно, — а
    выключал он его вчера именно затем, чтобы этого не было.
    """
    await runtime_settings.set_mode(BotMode.FULL)

    await window_module.prepare(session_factory)

    assert await runtime_settings.get_mode() is BotMode.OFF


def test_everything_is_put_out_from_the_top_down(opened):
    """Закрытое окно гасит слушателя, потом мост и только потом мотор.

    Слушатель первым: пока он жив, вторая копия получает от него обещание
    показать окно — а окна уже нет, и человек, нажавший ярлык, не увидит
    ничего.

    Мост раньше мотора: гашение моста отправляет остановку бота на мотор и
    ждёт её. Погасни мотор первым, этой работе некуда было бы уехать, и бот
    остался бы жив до конца процесса, держа базу и соединение с Telegram.
    """
    _fake, order = opened

    window_module.run_ui()

    assert order == ["слушатель", "мост", "мотор"]


def test_a_window_that_would_not_open_still_puts_the_bridge_out(opened, monkeypatch):
    """Окно, которое не поднялось, всё равно гасит за собой мост.

    Отказать подъём может на первом же чужом запуске — без WebView2 в системе.
    Пронесись отказ мимо гашения, бот остался бы работать до самой смерти
    процесса: с Telegram он не простился бы, а базу не отпустил.
    """
    fake, order = opened

    def refuse(**options):
        raise RuntimeError("WebView2 в системе нет")

    monkeypatch.setattr(fake, "start", refuse)

    with pytest.raises(RuntimeError):
        window_module.run_ui()

    assert order == ["слушатель", "мост", "мотор"]


async def test_a_finished_setup_opens_the_window_the_layout_needs(
    opened, runtime_settings
):
    """Настроенное приложение открывается не меньше того размера, под который
    нарисован экран.

    Ниже него разметка переносится и ломается, а вернуть размер человек уже не
    может: он тянет за край и упирается в то, что мы разрешили.
    """
    await runtime_settings.mark_wizard_completed()
    fake, _order = opened

    window_module.run_ui()

    # Числами, а не через саму величину: сверка константы с собой прошла бы и
    # на размере в сто точек, где разметка нечитаема вовсе.
    assert fake.created["min_size"] == (900, 660)
    assert fake.created["width"] == 900


def test_the_wizard_opens_in_a_smaller_window_it_cannot_stretch(opened):
    """Неоконченный мастер открывается своим окном, и потянуть его нельзя.

    Мастер нарисован под шестьсот сорок точек и на девятистах расплывается
    полосой пустоты. Растягивать в нём нечего — на экране одна колонка полей,
    — а свободный край дал бы человеку сплющить её до нечитаемого.
    """
    fake, _order = opened

    window_module.run_ui()

    assert fake.created["width"] == 640
    assert fake.created["height"] == 620
    assert fake.created["min_size"] == (640, 620)
    assert fake.created["resizable"] is False


def test_the_window_is_painted_before_the_page_opens(opened):
    """Окну назван цвет, которым система заливает его до страницы.

    Без этого довода pywebview заливает окно белым, и при растягивании — пока
    WebView2 не догнал новый размер — вместо оболочки видна ярко-белая вспышка
    со шлейфом прежнего кадра. Наблюдалось глазами на живом окне.
    """
    fake, _order = opened

    window_module.run_ui()

    # Значением, а не через саму постоянную: сверка её с собой прошла бы и на
    # белом, то есть ровно на том, из-за чего довод и появился.
    assert fake.created["background_color"] == "#2d2d2f"


def test_the_page_is_served_and_not_opened_from_the_disk(opened):
    """Страница отдаётся окну раздачей, а не открывается файлом с диска.

    С `file://` браузер отказывает и ввозу модулей, и запросам страницы — по
    правилам происхождения, — и отказ этот виден только в консоли: на экране
    просто пусто.
    """
    fake, _order = opened

    window_module.run_ui()

    assert callable(fake.created["url"])
