"""Откуда бот берёт свой режим.

Режим лежит в настройках и читается заново на каждом обороте цикла: окно
переключает его, пока бот работает, и запомненное значение означало бы, что
переключатель срабатывает только после перезапуска.

Сомнение здесь решается в пользу бездействия. Нечитаемый режим понимается как
«выключен»: продолжать рассылку, не зная, разрешена ли она, хуже, чем зря
постоять.
"""

from backend.models import BotMode


async def test_the_mode_comes_from_the_settings(make_bot):
    """Режим берётся из настроек, а не из памяти бота."""
    bot = await make_bot()
    await bot.rs.set_mode(BotMode.FULL)

    assert await bot.current_mode() is BotMode.FULL


async def test_an_unreadable_mode_reads_as_off(make_bot):
    """Нечитаемый режим понимается как «выключен».

    Продолжить рассылку, не зная, разрешена ли она, хуже, чем зря
    постоять.
    """
    bot = await make_bot()

    async def broken():
        raise OSError("база недоступна")

    bot.rs.get_mode = broken

    assert await bot.current_mode() is BotMode.OFF
