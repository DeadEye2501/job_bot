"""Следствия открытия и закрытия окна: что приложение делает вокруг него.

Самого окна здесь нет — его поднимает pywebview, а тому нужен настоящий рабочий
стол. Подменён он целиком: предмет тут не окно, а порядок вокруг него, и
ломается этот порядок молча.

Замеры того, чего подменой не проверить — параллельны ли зовы моста, переживает
ли ждущий зов закрытие окна, — сняты руками на живом pywebview и записаны в
плане, слайс А3.
"""

import logging
from concurrent.futures import Future

import pytest

from backend.repository.bot_mode import read_mode, write_mode
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


async def test_the_mode_outlives_a_restart(runtime_settings, session_factory):
    """Запуск застаёт режим таким, каким его вчера оставили.

    Режим — выбор человека, и стирать его при каждом открытии окна значит
    решать за него. На нём вдобавок держится переписка: в OFF бот молчит на
    все входящие письма, и сброшенный запуском режим гасил бы её до первого
    щелчка тумблером — каждое утро.
    """
    async with session_factory() as session:
        async with session.begin():
            await write_mode(session, BotMode.FULL)

    await window_module.prepare(session_factory)

    async with session_factory() as session:
        assert await read_mode(session) is BotMode.FULL


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


def test_a_shutdown_that_broke_does_not_look_like_a_failed_launch(
    opened, monkeypatch, caplog
):
    """Сорвавшееся гашение не выдаётся за несостоявшийся запуск.

    Гасить нечего: человек закрыл окно, приложение отработало, и процесс сейчас
    умрёт. А вот наружу такая беда уходила бы кодом отказа, и точка входа
    показала бы модальное «Не удалось запуститься» поверх уже закрытого окна —
    да ещё и держала бы процесс, пока его не нажмут.

    Сорвавшееся гашение при этом молчать не должно: движок, не отпустивший
    базу, виден только по журналу.
    """
    fake, _order = opened

    def hangs(*_args, **_kwargs):
        raise TimeoutError("движок не закрылся за отведённое время")

    monkeypatch.setattr(window_module.lifespan, "stop", hangs)

    with caplog.at_level(logging.ERROR, logger="client.window"):
        assert window_module.run_ui() == 0

    assert "движок не закрылся" in caplog.text


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


class _Settings:
    """Настройки ровно в том объёме, который читает снос файлов сеанса."""

    def __init__(self, *, has_tg_session: bool) -> None:
        self.has_tg_session = has_tg_session


def _sessions(tmp_path, monkeypatch):
    """Каталог сеансов с тремя файлами: два своих и один чужой."""
    where = tmp_path / "sessions"
    where.mkdir()
    for name in ("bot.session", "bot.session-journal", "заметка.txt"):
        (where / name).write_text("что-то", encoding="utf-8")
    monkeypatch.setattr("adapters.telegram.SESSIONS_DIR", where)
    return where


def test_a_live_session_makes_the_stale_files_go(tmp_path, monkeypatch):
    """Файлы сеанса рядом с базой сносятся, когда сеанс есть в самой базе.

    Ключ в них лежит открытым текстом, а в базе — зашифрованным; оставленные,
    они переживают и смену устройства, и забытый главный ключ.
    """
    where = _sessions(tmp_path, monkeypatch)

    window_module._drop_stale_session_files(_Settings(has_tg_session=True))

    assert sorted(one.name for one in where.iterdir()) == ["заметка.txt"]


def test_without_a_session_in_the_database_the_files_survive(tmp_path, monkeypatch):
    """Без сеанса в базе файлы остаются: они могут быть всем, что осталось.

    Мастер не дошёл до конца, базу пересоздали, ключ забыли — и снос оставил бы
    человека входить заново по коду, которого Telegram после нескольких попыток
    уже не пришлёт.
    """
    where = _sessions(tmp_path, monkeypatch)

    window_module._drop_stale_session_files(_Settings(has_tg_session=False))

    assert len(list(where.iterdir())) == 3
