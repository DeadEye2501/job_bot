"""Следствия мотора, в котором окно исполняет свою работу.

Окно живёт в своём потоке и ничего асинхронного само не умеет: всё, что
спрашивает мост, уезжает сюда. Стенд остальных проверок подменяет мотор
целиком — иначе движок базы, привязанный к циклу теста, до работы не доехал
бы, — и потому весь этот файл смотрит на настоящий мотор, а не на подмену.

Остановка проверяется отдельно: в ней отмена висящих задач, остановка цикла и
ожидание потока. Сломай любой из трёх шагов — и окно перестанет закрываться
либо оборвёт на середине закрытие Telegram и клиентов модели.
"""

import asyncio
import logging
import sqlite3
import threading

import pytest

from client.bridge.runner import AsyncRunner


@pytest.fixture
def real_runner():
    """Настоящий мотор, снимаемый после проверки.

    Имя отличается от общей фикстуры `runner` (`tests/client/conftest.py`)
    нарочно. Назовись она так же, она перекрывала бы общую на весь файл, и
    проверка, попросившая здесь `hub`, молча получила бы вместо подменённого
    мотора настоящий — с чужим циклом и своим потоком.

    Цикл закрывается здесь, а не остановкой: в бою за ней сразу умирает
    процесс, и закрывать его некому и незачем. В прогоне же незакрытый цикл
    оставляет за собой пару сокетов на каждую проверку.
    """
    made = AsyncRunner()
    yield made
    made.stop()
    made.loop.close()


def test_work_sent_to_the_runner_is_done(real_runner):
    """Отправленная работа исполняется, и ответ доезжает обратно."""

    async def answer():
        return "готово"

    assert real_runner.submit(answer()).result(timeout=5) == "готово"


def test_the_work_runs_in_its_own_thread(real_runner):
    """Работа идёт не в потоке окна, а в своём.

    Иначе долгий обход каналов замораживал бы окно целиком.
    """

    async def whose_thread():
        return threading.current_thread().name

    where = real_runner.submit(whose_thread()).result(timeout=5)

    assert where != threading.current_thread().name


def test_stopping_cancels_the_work_left_hanging(real_runner):
    """Остановка отменяет висящую работу, а не бросает её вместе с циклом.

    В `finally` у бота стоят отключение Telegram и закрытие клиентов модели.
    Не получи задача отмены — цикл умер бы раньше них, и приложение оставило
    бы за собой открытое соединение.
    """
    made = real_runner
    cancelled = threading.Event()

    async def long_work():
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    made.submit(long_work())
    # Задача должна успеть дойти до ожидания: отменять ещё не начатую нечего.
    made.submit(asyncio.sleep(0)).result(timeout=5)

    made.stop()

    assert cancelled.is_set()


def test_stopping_lets_the_loop_go(real_runner):
    """После остановки цикл мотора не работает.

    Оставшийся работать, он держит приложение живым после закрытия окна.
    """
    made = real_runner
    made.submit(asyncio.sleep(0)).result(timeout=5)

    made.stop()

    assert not made.loop.is_running()


def test_stopping_twice_is_not_a_trouble(real_runner):
    """Вторая остановка ничего не ломает.

    Закрытие окна и снос данных зовут её порознь, и порядок между ними не
    закреплён ничем.
    """
    real_runner.stop()

    real_runner.stop()


def _troubled(real_runner, exc: BaseException) -> None:
    """Отдать мотору беду, которую никто не перехватил.

    Сперва дожидаемся самого цикла: ставит обработчик уже фоновый поток, а
    `Thread.start` возвращает управление раньше, чем тот до этого доходит.
    Без ожидания проверка изредка мигала бы на пустом месте — и искать причину
    пришлось бы в поломке, которой нет.
    """
    real_runner.submit(asyncio.sleep(0)).result(timeout=5)
    handler = real_runner.loop.get_exception_handler()
    handler(real_runner.loop, {"exception": exc, "message": "беда в цикле"})


def test_a_shutdown_race_of_pyrogram_is_swallowed_with_a_word(real_runner, caplog):
    """Шум гашения Pyrogram глушится, но не молча.

    Pyrogram догоняет обновлением уже закрытую базу и остановленный цикл, и
    делать с этим нечего — применять некуда. Но всплыви та же беда не при
    гашении, и это значит, что базу или цикл закрыли рано: тихая отладка
    спрятала бы это, поэтому здесь предупреждение.
    """
    with caplog.at_level(logging.DEBUG, logger="client.bridge.runner"):
        _troubled(real_runner, sqlite3.ProgrammingError("Cannot operate on a closed database."))
        _troubled(real_runner, RuntimeError("Event loop is closed"))
        _troubled(real_runner, AttributeError("'Client' object has no attribute 'storage'"))

    assert caplog.text.count("swallowed") == 3
    # И не пропущены дальше: пропусти обработчик контекст в штатный, журнал
    # засыпало бы трассировками гонки Pyrogram на каждом закрытии окна.
    assert [one for one in caplog.records if one.name == "asyncio"] == []


def test_a_real_trouble_in_the_loop_reaches_the_log(real_runner, caplog):
    """Беда, не похожая на шум гашения, доезжает до журнала целиком.

    Экран «Логи» — единственная диагностика этого приложения. Сделай фильтр
    шире, и всякая неперехваченная беда мотора пропадала бы молча; сделай уже —
    и каждое закрытие окна засыпало бы журнал трассировками гонки Pyrogram, за
    которыми настоящие записи утонут.
    """
    with caplog.at_level(logging.ERROR, logger="asyncio"):
        _troubled(real_runner, ValueError("а вот это настоящая поломка"))

    assert "а вот это настоящая поломка" in caplog.text


def test_a_closed_database_outside_a_shutdown_is_not_swallowed(real_runner, caplog):
    """Закрытая база, названная другими словами, за шум не принимается.

    Глушится не порода беды, а именно гонка гашения: та же порода с другим
    текстом — это наша поломка, и прятать её нельзя.
    """
    with caplog.at_level(logging.ERROR, logger="asyncio"):
        _troubled(real_runner, sqlite3.ProgrammingError("no such column: hr.name"))

    assert "no such column" in caplog.text
