"""Следствия выхода из учётной записи Telegram.

Пользователь нажал «выйти» — значит бот должен остановиться, чем бы ни
кончился сам запрос к серверу. Сессию Telegram отзывает у себя, а бот вдобавок
будит свой цикл: без побудки просьба остановиться дошла бы только к концу
получасового сна, и всё это время он сидел бы с отозванной сессией.
"""

from tests.fakes.telegram import FakeTelegramClient


async def test_logging_out_stops_the_bot(make_bot):
    """Выход из учётной записи отзывает сессию и останавливает бота."""
    client = FakeTelegramClient()
    bot = await make_bot(client)

    await bot.log_out_session()

    assert client.logged_out is True
    assert bot._stop_event.is_set()
    assert bot._wake_event.is_set()


async def test_a_failed_log_out_stops_the_bot_anyway(make_bot):
    """Сорвавшийся выход всё равно останавливает бота.

    Пользователь нажал «выйти»: оставить его с работающим ботом из-за
    неудачного запроса значило бы не сделать ровно то, о чём просили.
    """
    bot = await make_bot(FakeTelegramClient(fails={"log_out": OSError("сеть")}))

    await bot.log_out_session()

    assert bot._stop_event.is_set()
    assert bot._wake_event.is_set()
