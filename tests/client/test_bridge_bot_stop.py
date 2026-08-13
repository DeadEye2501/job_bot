"""Следствия остановки бота: чем кончается ожидание, которого не дождались.

Три дороги гасят бота — закрытие окна, выход из учётной записи и снос данных, —
и все три идут дальше независимо от того, остановился он или завис. Проверяется
здесь именно это: зависшая работа не держит человека и не отменяет того, ради
чего бота гасили.
"""

import asyncio
from concurrent.futures import Future

import pytest

from client.bridge.bot_stop import stop_bot


class HangingBot:
    """Бот, который просьбу слышит, а работу не заканчивает."""

    def __init__(self) -> None:
        self.asked: list[str] = []

    def cancel_current_poll(self) -> None:
        self.asked.append("cancel")

    def request_stop(self) -> None:
        self.asked.append("stop")


async def test_a_bot_that_never_stops_does_not_hold_the_caller():
    """Не дождавшись бота, остановка всё равно отдаёт управление.

    Иначе закрытие окна висело бы до конца зависшего обхода — то есть, с точки
    зрения человека, не закрывалось бы вовсе.
    """
    bot = HangingBot()
    never = Future()

    await asyncio.wait_for(stop_bot(bot, never, timeout=0.01), timeout=1)

    assert bot.asked == ["cancel", "stop"]


async def test_a_failed_request_reaches_the_caller():
    """Сорвавшаяся просьба доезжает до зовущего, а не тонет в журнале.

    Выход из учётной записи обязан сказать окну, что ключ на сервере отозвать
    не вышло: молчание здесь значит «вы вышли», а сеанс при этом жив.
    """

    async def refusing() -> None:
        raise RuntimeError("сервер не ответил")

    with pytest.raises(RuntimeError, match="сервер не ответил"):
        await stop_bot(HangingBot(), None, refusing)
