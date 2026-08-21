"""Следствия просьбы второй копии вывести вперёд уже открытое окно.

Замок не пускает вторую копию работать, и сказать ей о себе нечем: в боевой
сборке нет ни консоли, ни потока ошибок. Человек жмёт ярлык второй раз и ждёт
окна — значит показать надо то, которое уже открыто, а не сообщение о том,
почему нового не будет.

Разговаривают копии по петлевому сокету: он же и опознаёт живую копию —
дозвониться удаётся только до слушающей, а признаёт она себя тем, что отвечает
на своё имя.
"""

import socket
from pathlib import Path

import pytest

import client.raise_window as raise_window
from client.raise_window import LOOPBACK, ask_to_raise, listen


class WindowDouble:
    """Окно, которое умеет только то, чем его выводят вперёд."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def restore(self) -> None:
        self.calls.append("развернуть")

    def show(self) -> None:
        self.calls.append("показать")


@pytest.fixture
def copies():
    """Заводит слушателей и гасит их в конце.

    Брошенный слушатель пережил бы тест: его держит свой поток, а порт он
    отпускает только закрытым, и следующий тест на то же имя не занял бы его.
    """
    started = []

    def start(window, name):
        server = listen(window, name)
        started.append(server)
        return server

    yield start
    for server in started:
        server.close()


def test_nobody_listening_means_nobody_to_ask():
    """Некому передать просьбу — так и говорится.

    По этому ответу зовущий понимает, что живой копии за замком нет. Соври
    здесь «передал» — и человек ждал бы окна, которое никто не покажет.
    """
    assert ask_to_raise("job-bot-проверка-никто-не-слушает") is False


def test_a_listening_copy_brings_its_window_forward(copies):
    """Слушающая копия по просьбе выводит своё окно вперёд.

    Сперва разворачивается свёрнутое: поднимать свёрнутое бесполезно, оно
    останется в панели задач, и человек решит, что второй запуск не сделал
    ничего. Порядок здесь и есть следствие — показ после разворота.

    Ответ приходит уже после того, как окно тронуто, поэтому проверять его
    можно сразу: «передал» значит «показал».
    """
    window = WindowDouble()
    copies(window, "job-bot-проверка-слушающей-копии")

    assert ask_to_raise("job-bot-проверка-слушающей-копии") is True
    assert window.calls == ["развернуть", "показать"]


def test_a_port_left_by_a_dead_copy_does_not_block_listening(copies):
    """Порт, оставленный умершей копией, слушать не мешает.

    Копия уходит, не дождавшись, пока система отпустит порт до конца. Не займи
    его следующий запуск — просьбы уходили бы в никуда, пока система не остынет
    сама.

    Брошенную копию доводим до настоящего разговора, а не открываем и закрываем
    пустой: порт остывает только после соединения, и без него сторож проверял
    бы, что свободный порт можно занять дважды.
    """
    name = "job-bot-проверка-брошенного-порта"
    abandoned_window = WindowDouble()
    abandoned = copies(abandoned_window, name)
    assert ask_to_raise(name) is True
    assert abandoned_window.calls == ["развернуть", "показать"]
    abandoned.close()

    window = WindowDouble()
    copies(window, name)

    assert ask_to_raise(name) is True
    assert window.calls == ["развернуть", "показать"]


def test_a_stranger_on_the_port_is_not_a_copy_of_ours():
    """Чужой на нашем порту за открытую копию не считается.

    Порт выведен из имени, и занять его до нас может кто угодно. Прими его за
    свою копию — и зовущий сказал бы «передал», хотя окна не покажет никто.
    """
    name = "job-bot-проверка-чужого-на-порту"
    stranger = socket.socket()
    stranger.bind((LOOPBACK, raise_window.port_of(name)))
    stranger.listen(1)
    try:
        assert ask_to_raise(name) is False
    finally:
        stranger.close()


def test_a_greeting_from_a_stranger_leaves_the_window_alone(copies):
    """Подключение не своим именем окна не поднимает.

    На петлевой порт стучится не только наша копия: любой обход портов открыл
    бы человеку окно посреди чужой работы.
    """
    name = "job-bot-проверка-чужого-приветствия"
    window = WindowDouble()
    copies(window, name)

    with socket.create_connection((LOOPBACK, raise_window.port_of(name)), 1.0) as sock:
        sock.sendall(b"x" * len(name.encode("utf-8")))
        answer = sock.recv(16)

    assert answer == b""
    assert window.calls == []


def test_the_socket_name_follows_the_data_directory(monkeypatch):
    """Имя сокета своё у каждого каталога данных.

    Замок — покаталожный, и две копии над разными каталогами он пускает
    нарочно. Общее имя на машину развело бы их с замком: договариваться они
    стали бы через одно имя, и одна из двух не смогла бы слушать вовсе.
    """
    monkeypatch.setattr(raise_window, "get_data_dir", lambda: Path("/один"))
    first = raise_window.socket_name()
    monkeypatch.setattr(raise_window, "get_data_dir", lambda: Path("/другой"))

    assert raise_window.socket_name() != first


def test_a_port_follows_the_socket_name():
    """Разным именам — разные порты.

    Общий порт на все имена свёл бы две копии над разными каталогами данных в
    один разговор: просьба к одной поднимала бы окно другой.
    """
    assert raise_window.port_of("job-bot-один") != raise_window.port_of("job-bot-другой")
