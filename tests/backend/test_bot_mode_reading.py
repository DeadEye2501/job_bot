"""Откуда бот берёт свой режим.

Режим лежит в настройках и читается заново на каждом обороте цикла: окно
переключает его, пока бот работает, и запомненное значение означало бы, что
переключатель срабатывает только после перезапуска.

Сомнение здесь решается в пользу бездействия. Нечитаемый режим понимается как
«выключен»: продолжать рассылку, не зная, разрешена ли она, хуже, чем зря
постоять.
"""

from backend.bot import loop
from backend.models import BotMode
from tests.backend.fixtures.bot import switch_to


async def test_the_mode_comes_from_the_base(make_bot, session_factory):
    """Режим берётся из базы, а не из памяти бота."""
    bot = await make_bot()
    await switch_to(session_factory, BotMode.FULL)

    assert await bot.current_mode() is BotMode.FULL


async def test_an_unreadable_mode_reads_as_off(make_bot, monkeypatch):
    """Нечитаемый режим понимается как «выключен».

    Продолжить рассылку, не зная, разрешена ли она, хуже, чем зря
    постоять.
    """
    bot = await make_bot()

    async def broken(session):
        raise OSError("база недоступна")

    monkeypatch.setattr(loop, "read_mode", broken)

    assert await bot.current_mode() is BotMode.OFF
