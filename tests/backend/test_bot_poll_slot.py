"""Следствия ручного прогона, запущенного кнопкой окна.

Прогон занимает единственное место: два одновременных цикла подрались бы за
кэш векторов и за курсор канала. Занятое место — не ошибка, а отказ, о
котором окно говорит подсказкой.

Место освобождается всегда — и после успеха, и после отмены, и после сбоя, —
иначе кнопка «прогнать» замирает навсегда. По той же причине всегда
досматривается до конца оповещение о завершении цикла: без него нижняя
полоса окна остаётся крутиться.
"""

import asyncio

import pytest

from backend.models import BotMode
from tests.backend.fixtures.bot import switch_to
from tests.fakes.ingestion import FakeIngestion, WindowHooks, wire


async def test_a_manual_channel_poll_reports_success(make_bot):
    """Прогон одного канала, дошедший до конца, сообщает об успехе."""
    ingestion = FakeIngestion()
    bot = wire(await make_bot(), ingestion)

    assert await bot.poll_channel_now(7) == "ok"
    assert ingestion.channel_calls == [7]
    assert bot.current_poll_task is None


async def test_a_channel_the_pipeline_could_not_take_reports_missing(make_bot):
    """Канал, который конвейер не взял, отдаёт «не найден».

    Так окно скажет про удалённую строку или канал без имени по-своему,
    а не общей «ошибкой».
    """
    bot = wire(await make_bot(), FakeIngestion(word_outcome="missing"))

    assert await bot.poll_channel_now(7) == "missing"


async def test_a_manual_channel_poll_while_busy_is_refused(make_bot, busy_slot):
    """Второй прогон при занятом месте отказывается, а не встаёт рядом.

    Два цикла разом дерутся за кэш векторов и курсор канала.
    """
    ingestion = FakeIngestion()
    bot = wire(await make_bot(), ingestion)
    busy_slot(bot)

    assert await bot.poll_channel_now(7) == "busy"
    assert ingestion.channel_calls == []



async def test_a_cancelled_channel_poll_frees_the_slot(make_bot):
    """Отменённый прогон освобождает место и сообщает об отмене.

    Не освободив, кнопка «прогнать» замерла бы навсегда: занятость
    проверяется по тому же полю.
    """
    bot = wire(await make_bot(), FakeIngestion(hangs=True))
    running = asyncio.create_task(bot.poll_channel_now(7))
    await asyncio.sleep(0)
    bot.cancel_current_poll()

    assert await running == "cancelled"
    assert bot.current_poll_task is None


async def test_cancelling_the_whole_loop_is_not_taken_for_a_cancelled_poll(
    make_bot,
):
    """Отмена самого цикла отменой прогона не считается и уходит наружу.

    Окно, закрываясь, отменяет работу целиком. Прими место прогона эту отмену
    за свою — цикл спокойно пошёл бы дальше и погасил соединения под живой
    задачей обхода: та осталась бы читать канал и писать в закрытую базу.
    """
    bot = wire(await make_bot(), FakeIngestion(hangs=True))
    running = asyncio.create_task(bot.poll_channel_now(7))
    await asyncio.sleep(0)

    running.cancel()

    with pytest.raises(asyncio.CancelledError):
        await running
    assert bot.current_poll_task is None


async def test_a_failed_channel_poll_frees_the_slot_too(make_bot):
    """Сбой прогона тоже освобождает место и сообщает об ошибке."""
    bot = wire(await make_bot(), FakeIngestion(error=RuntimeError("сорвалось")))

    assert await bot.poll_channel_now(7) == "error"
    assert bot.current_poll_task is None


@pytest.mark.parametrize(
    "error",
    [pytest.param(None, id="успех"), pytest.param(RuntimeError("сорвалось"), id="сбой")],
)
async def test_the_window_hears_both_ends_of_a_channel_poll(make_bot, error):
    """Окно узнаёт и о начале, и о конце прогона — чем бы тот ни кончился.

    На оповещении о конце гаснет крутящаяся полоса внизу окна.
    """
    hooks = WindowHooks()
    bot = wire(await make_bot(), FakeIngestion(error=error), hooks)

    await bot.poll_channel_now(7)

    assert hooks.log == ["начало", "конец"]
    # Полоса с долей сделанного — примета одного только ручного прогона
    # вакансии: у обхода канала шкалы нет, и трогать её незачем.
    assert hooks.progress == []


async def test_a_broken_start_hook_does_not_stop_the_poll(make_bot):
    """Сломанное оповещение о начале прогон не отменяет.

    Оно только красит полосу в окне; из-за него не запустить сбор
    вакансий было бы обменом важного на украшение.
    """
    ingestion = FakeIngestion()
    bot = wire(await make_bot(), ingestion, WindowHooks(start_error=RuntimeError("окно")))

    assert await bot.poll_channel_now(7) == "ok"
    assert ingestion.channel_calls == [7]


async def test_a_broken_end_hook_does_not_change_the_outcome(make_bot):
    """Сломанное оповещение о конце не меняет исход прогона."""
    bot = wire(await make_bot(), FakeIngestion(), WindowHooks(end_error=RuntimeError("окно")))

    assert await bot.poll_channel_now(7) == "ok"
    assert bot.current_poll_task is None


async def test_a_forced_full_poll_reports_success(make_bot):
    """Полный прогон по кнопке обновления доходит до конца и сообщает успех."""
    ingestion = FakeIngestion()
    bot = wire(await make_bot(), ingestion)

    assert await bot.force_poll_once() == "ok"
    assert ingestion.full_calls == 1
    assert bot.current_poll_task is None


@pytest.fixture
def launched(monkeypatch) -> list:
    """Обход агрегаторов подменён: в списке — боты, которым его запустили."""
    bots = []

    async def launch(bot):
        bots.append(bot)

    monkeypatch.setattr("backend.bot.aggregators.launch_round", launch)
    return bots


async def test_a_forced_poll_is_the_same_turn_as_the_cycle(make_bot, launched, session_factory):
    """Кнопка ▶ — тот же оборот, что у цикла: подбор недоразобранного, каналы,
    затем обход агрегаторов. Режим её не держит: бот выключен — она всё равно идёт."""
    ingestion = FakeIngestion()
    bot = wire(await make_bot(), ingestion)
    await switch_to(session_factory, BotMode.OFF)

    assert await bot.force_poll_once() == "ok"
    assert ingestion.log[:2] == ["недоразобранные", "прогон каналов"]
    assert launched == [bot]


async def test_the_forced_poll_itself_does_not_stop_at_switched_off_channels(
    make_bot, launched
):
    """Выключенные каналы ▶ не останавливают: опрашивать там нечего, а оборот
    идёт дальше к агрегаторам и кончается удачей.

    Опрос каналов здесь подделан, и выключатель, который действует внутри него,
    не на пути. Сторожит тест другое: что сама кнопка выключатель каналов не
    спрашивает и оборот из-за него не обрывает."""
    bot = wire(await make_bot(), FakeIngestion())
    await bot.rs.set_app("channels_enabled", "false")

    assert await bot.force_poll_once() == "ok"
    assert launched == [bot]


async def test_a_forced_full_poll_while_busy_is_refused(make_bot, busy_slot):
    """Полный прогон при занятом месте отказывается."""
    ingestion = FakeIngestion()
    bot = wire(await make_bot(), ingestion)
    busy_slot(bot)

    assert await bot.force_poll_once() == "busy"
    assert ingestion.full_calls == 0



async def test_a_cancelled_full_poll_frees_the_slot(make_bot):
    """Отменённый полный прогон освобождает место и сообщает об отмене."""
    bot = wire(await make_bot(), FakeIngestion(hangs=True))
    running = asyncio.create_task(bot.force_poll_once())
    await asyncio.sleep(0)
    bot.cancel_current_poll()

    assert await running == "cancelled"
    assert bot.current_poll_task is None


async def test_a_failed_full_poll_frees_the_slot_too(make_bot):
    """Сбой полного прогона тоже освобождает место и сообщает об ошибке."""
    bot = wire(await make_bot(), FakeIngestion(error=RuntimeError("сорвалось")))

    assert await bot.force_poll_once() == "error"
    assert bot.current_poll_task is None


async def test_the_window_hears_both_ends_of_a_full_poll(make_bot):
    """Окно узнаёт и о начале, и о конце полного прогона."""
    hooks = WindowHooks()
    bot = wire(await make_bot(), FakeIngestion(), hooks)

    await bot.force_poll_once()

    assert hooks.log == ["начало", "конец"]
