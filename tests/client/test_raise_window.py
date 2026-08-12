"""Следствия просьбы второй копии вывести вперёд уже открытое окно.

Замок не пускает вторую копию работать, и сказать ей о себе нечем: в боевой
сборке нет ни консоли, ни потока ошибок. Человек жмёт ярлык второй раз и ждёт
окна — значит показать надо то, которое уже открыто, а не сообщение о том,
почему нового не будет.

Разговаривают копии по локальному сокету: он же и опознаёт живую копию —
подключиться удаётся только к слушающей.
"""

from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication

from client.raise_window import ask_to_raise, listen


class WindowDouble:
    """Окно, которое умеет только то, чем его выводят вперёд."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def isMinimized(self) -> bool:
        return False

    def showNormal(self) -> None:
        self.calls.append("развернуть")

    def raise_(self) -> None:
        self.calls.append("поднять")

    def activateWindow(self) -> None:
        self.calls.append("в фокус")


@pytest.fixture
def qt_alive():
    """Приложение Qt: без него слушателю нечем разбирать подключения.

    Просящей стороне оно не нужно — `waitForConnected` крутит свой цикл, и
    боевой зов из `main()` идёт как раз без приложения. А вот сигнал о новом
    подключении доставляет цикл событий, и без приложения крутить его нечем.

    Заводится одно на прогон и не гасится: второго `QCoreApplication` в том же
    процессе Qt не позволяет, а гашение первого унесло бы с собой всё, что
    успели создать.
    """
    return QCoreApplication.instance() or QCoreApplication([])


def test_nobody_listening_means_nobody_to_ask(qt_alive):
    """Некому передать просьбу — так и говорится.

    По этому ответу зовущий понимает, что живой копии за замком нет. Соври
    здесь «передал» — и человек ждал бы окна, которое никто не покажет.
    """
    assert ask_to_raise("job-bot-проверка-никто-не-слушает") is False


def test_a_listening_copy_brings_its_window_forward(qt_alive):
    """Слушающая копия по просьбе выводит своё окно вперёд.

    Окно поднимается над чужими и получает фокус: без фокуса оно всплывёт, но
    ввод останется у той программы, поверх которой человек нажал ярлык.
    """
    window = WindowDouble()
    server = listen(window, "job-bot-проверка-слушающей-копии")

    assert ask_to_raise("job-bot-проверка-слушающей-копии") is True

    # Подключение доезжает до слушающего оборотом цикла событий, а не вызовом:
    # сразу после просьбы окно ещё не тронуто, и утверждение соврало бы.
    qt_alive.processEvents()
    assert window.calls == ["поднять", "в фокус"]

    server.close()


def test_a_minimized_window_is_unminimized_first(qt_alive):
    """Свёрнутое окно сперва разворачивают.

    Поднимать свёрнутое бесполезно: оно останется в панели задач, и человек
    решит, что второй запуск не сделал ничего.
    """
    window = WindowDouble()
    window.isMinimized = lambda: True
    server = listen(window, "job-bot-проверка-свёрнутого-окна")

    ask_to_raise("job-bot-проверка-свёрнутого-окна")

    qt_alive.processEvents()
    assert window.calls == ["развернуть", "поднять", "в фокус"]

    server.close()


def test_a_name_left_by_a_dead_copy_does_not_block_listening(qt_alive):
    """Имя, брошенное умершей копией, слушать не мешает.

    Вне Windows сокет остаётся файлом и переживает падение процесса. Не сними
    его — и следующий запуск не занял бы имя, а просьбы второй копии уходили бы
    в никуда до тех пор, пока файл не удалят руками.

    Брошенное имя изображается закрытым сервером: `close()` на unix оставляет
    файл сокета, как его оставила бы умершая копия.
    """
    name = "job-bot-проверка-брошенного-имени"
    abandoned = listen(WindowDouble(), name)
    abandoned.close()

    window = WindowDouble()
    second = listen(window, name)

    assert second.isListening()
    assert ask_to_raise(name) is True
    qt_alive.processEvents()
    assert window.calls == ["поднять", "в фокус"]

    second.close()


def test_the_socket_name_follows_the_data_directory(monkeypatch):
    """Имя сокета своё у каждого каталога данных.

    Замок — покаталожный, и две копии над разными каталогами он пускает
    нарочно. Общее имя на машину развело бы их с замком: договариваться они
    стали бы через одно имя, и одна из двух не смогла бы слушать вовсе.
    """
    import client.raise_window as module

    monkeypatch.setattr(module, "get_data_dir", lambda: Path("/один"))
    first = module.socket_name()
    monkeypatch.setattr(module, "get_data_dir", lambda: Path("/другой"))

    assert module.socket_name() != first
