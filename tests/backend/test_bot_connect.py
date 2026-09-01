"""Следствия подъёма соединения с Telegram.

Кэш пиров живёт в памяти вместе со строкой сеанса и пуст при каждом запуске
приложения, а собеседника мы адресуем номером учётной записи: по пустому кэшу
он не разрешается, и Telegram отвечает `PeerIdInvalid` — чтению переписки,
отправке письма и отметке о прочтении разом. Поэтому подъём греет кэш, и
греет до того, как объявит бота готовым: окно, узнавшее о готовом боте, шлёт
письма сразу.

Оборот цикла проверяется отдельно, в `test_bot_run_loop.py`: там предмет —
что бот делает в каждом режиме, здесь — с чем он выходит из подъёма.
"""

import pytest

from backend.models import BotMode, Message
from tests.backend.fixtures.backfill import theirs
from tests.dbio import all_rows
from tests.fakes.ingestion import FakeIngestion, wire
from tests.fakes.telegram import FakeTelegramClient


@pytest.fixture
def caught_up(monkeypatch):
    """Подменяет догон пропущенных писем: он живёт в конвейере."""
    calls: list[dict] = []

    async def catch_up_missed_dms(client, *args, **kwargs):
        calls.append(kwargs)

    monkeypatch.setattr("backend.bot.loop.catch_up_missed_dms", catch_up_missed_dms)
    return calls


async def test_a_cold_session_reads_the_history_of_a_nameless_hr(
    chatting, session_factory
):
    """Переписка догоняется, когда у собеседника есть номер и нет ника.

    Кэш пиров Pyrogram живёт в памяти и пуст при каждом запуске приложения:
    чтение по номеру отвечает `PeerIdInvalid`. Лечили это розыском по нику, но
    ника у собеседника может не быть вовсе — и тогда его переписка не читается
    ни разу за весь сеанс.
    """
    client = FakeTelegramClient()
    client.cold_peers = {777}
    client.history = [theirs(9, "здравствуйте")]
    bot, _, _ = await chatting(
        mode=BotMode.DM_ONLY,
        client=client,
        telegram_user_id=777,
        telegram_username=None,
    )

    await bot.run(once=True)

    stored = await all_rows(session_factory, Message)
    assert [m.tg_message_id for m in stored] == [9]


async def test_a_broken_warm_up_does_not_stop_the_bot(chatting, caught_up):
    """Сорвавшийся прогрев кэша подъём не отменяет.

    Без прогрева приложение работает так же, как работало до него; ронять
    из-за него соединение значило бы менять «переписка читается медленно» на
    «не работает вовсе ничего».
    """
    client = FakeTelegramClient(fails={"invoke": OSError("сеть отвалилась")})
    bot, _, _ = await chatting(mode=BotMode.DM_ONLY, client=client)
    wire(bot, FakeIngestion())

    await bot.run(once=True)

    assert client.lifecycle == ["запуск", "остановка"]


async def test_the_bot_is_declared_ready_only_after_the_cache_is_warm(
    chatting, caught_up
):
    """Готовность объявляется после прогрева, а не до.

    Окно, узнавшее о готовом боте, шлёт письмо сразу — и по холодному кэшу
    оно падает `PeerIdInvalid`. Перенеси прогрев за объявление готовности, и
    эта дыра вернётся молча.
    """
    client = FakeTelegramClient()
    bot, _, _ = await chatting(mode=BotMode.DM_ONLY, client=client)
    wire(bot, FakeIngestion())
    seen: list[bool] = []
    invoke = client.invoke

    async def invoke_and_look(query, **options):
        seen.append(bot.is_ready)
        return await invoke(query, **options)

    client.invoke = invoke_and_look

    await bot.run(once=True)

    assert seen == [False]
