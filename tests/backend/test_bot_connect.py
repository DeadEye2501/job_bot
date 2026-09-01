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

import asyncio

from backend.models import BotMode, Message
from tests.backend.fixtures.backfill import theirs
from tests.dbio import all_rows
from tests.fakes.ingestion import FakeIngestion, wire
from tests.fakes.telegram import FakeTelegramClient


async def test_a_cold_session_reads_the_history_of_a_nameless_hr(
    chatting, session_factory, turn_and_settle
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

    await turn_and_settle(bot, BotMode.DM_ONLY)

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


async def test_a_dialog_page_that_never_moves_ends_the_warm_up(chatting):
    """Прогрев кончается, даже когда список переписок не двигается.

    Закладку следующей страницы прогрев считает по верхнему письму, а того в
    ответе может не оказаться вовсе: у стёртого письма Telegram кладёт
    `messageEmpty`, у пустой переписки номер нулевой. Нулевая закладка значит
    «с самого верха» — и без сторожа продвижения прогрев ходил бы по кругу.

    Ходил бы он в подъёме, до объявления готовности: окно ждало бы готового
    бота вечно, и ни строки в журнале об этом не было бы.
    """
    client = FakeTelegramClient()
    client.dialog_page = list(range(1, 101))
    bot, _, _ = await chatting(mode=BotMode.OFF, client=client)
    wire(bot, FakeIngestion())

    await asyncio.wait_for(bot.run(once=True), timeout=5)

    assert client.lifecycle == ["запуск", "остановка"]


async def test_a_broken_dialog_read_still_catches_everyone_up(
    chatting, monkeypatch, turn_and_settle
):
    """Сорвавшееся чтение переписок догон не отменяет, а лишает порядка.

    Список правит очередь, а не решает, идти ли вообще: не прочитав его, догон
    обязан пойти по всем известным собеседникам — медленно, как ходил раньше,
    но не мимо. Сорваться же чтению есть от чего: долгое «слишком часто» от
    Telegram вылетает наружу, и приходит оно как раз тогда, когда переписки
    больше всего и ждут.
    """
    caught: list[dict] = []

    async def catch_up_missed_dms(client, *args, **kwargs):
        caught.append(kwargs)

    async def read_dialogs(client):
        raise OSError("сеть отвалилась")

    monkeypatch.setattr("backend.bot.loop.catch_up_missed_dms", catch_up_missed_dms)
    monkeypatch.setattr("adapters.telegram.list_dialog_peers", read_dialogs)
    bot, _, _ = await chatting(mode=BotMode.DM_ONLY)
    wire(bot, FakeIngestion())

    await turn_and_settle(bot, BotMode.DM_ONLY)

    assert [one["dialogs"] for one in caught] == [[]]


async def test_a_handle_from_the_dialog_list_reaches_the_queue(chatting, caught_up,
                                                               turn_and_settle):
    """Ник из ответа Telegram доезжает до очереди догона.

    По нему опознают собеседника, у которого номера учётной записи нет вовсе,
    — так заводит его разбор объявления, где в посте стоит один `@ник`. Не
    разбери мы ники из ответа, такой собеседник уехал бы в хвост очереди, и
    его письмо не подгружалось бы, пока очередь до него не дойдёт.
    """
    client = FakeTelegramClient()
    client.dialog_page = [500]
    client.nicks = {500: "Mastakova_TeamLead"}
    bot, _, _ = await chatting(mode=BotMode.DM_ONLY, client=client)
    wire(bot, FakeIngestion())

    await turn_and_settle(bot, BotMode.DM_ONLY)

    assert [(one.peer_id, one.username) for one in caught_up[0]["dialogs"]] == [
        (500, "Mastakova_TeamLead")
    ]

