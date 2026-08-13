"""Следствия вопроса «живо ли то, на чём держится работа».

Ответ на него рисует лампочка в шапке окна, и цена ошибки здесь несимметрична:
погасшая зря лампочка отправляет человека чинить работающее, а горящая зря —
оставляет его в уверенности, что всё в порядке, пока бот молчит.
"""

from backend.health import database_alive, telegram_alive


class Stopped:
    """Фабрика сессий, у которой движок уже закрыт."""

    def __call__(self):
        raise RuntimeError("Engine is disposed")


class Bot:
    def __init__(self, connected: bool) -> None:
        self.is_connected = connected


async def test_a_closed_engine_darkens_the_lamp(session_factory):
    """Закрытый движок гасит лампочку базы, а не уносит весь ответ.

    Движок закрывают на сносе данных, и тик часов после этого приходит на
    пустое место. Выброс отсюда унёс бы ответ целиком — окно молча выбросило
    бы его, и человек смотрел бы на застывшую зелёную лампочку.
    """
    assert await database_alive(session_factory) is True
    assert await database_alive(Stopped()) is False


def test_a_bot_that_is_not_there_is_not_healthy():
    """Бота нет — Telegram не здоров, а не «неизвестно».

    До входа в учётную запись бота не существует вовсе. Считай мост это
    неизвестностью — лампочка горела бы зелёной на пустом месте.
    """
    assert telegram_alive(None) is False
    assert telegram_alive(Bot(connected=False)) is False
    assert telegram_alive(Bot(connected=True)) is True
