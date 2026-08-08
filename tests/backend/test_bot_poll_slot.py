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


class _Ingestion:
    """Подделка конвейера: сообщает, чем кончился прогон, и считает заходы."""

    def __init__(self, *, outcome=True, error=None, hangs=False) -> None:
        self._outcome = outcome
        self._error = error
        self._hangs = hangs
        self.channel_calls: list[int] = []
        self.full_calls = 0

    async def poll_one_channel(self, channel_id: int):
        self.channel_calls.append(channel_id)
        return await self._run()

    async def poll_active_channels(self):
        self.full_calls += 1
        return await self._run()

    async def _run(self):
        if self._hangs:
            await asyncio.sleep(30)
        if self._error is not None:
            raise self._error
        return self._outcome


class _Hooks:
    """Оповещения окна о начале и конце цикла."""

    def __init__(self, *, start_error=None, end_error=None) -> None:
        self._start_error = start_error
        self._end_error = end_error
        self.log: list[str] = []

    def start(self) -> None:
        self.log.append("начало")
        if self._start_error is not None:
            raise self._start_error

    def end(self) -> None:
        self.log.append("конец")
        if self._end_error is not None:
            raise self._end_error


def _wire(bot, ingestion, hooks=None):
    """Подменяет конвейер и подключает оповещения окна."""
    bot._ingestion = ingestion
    if hooks is not None:
        bot.on_cycle_start = hooks.start
        bot.on_cycle_end = hooks.end
    return bot


async def test_a_manual_channel_poll_reports_success(make_bot):
    """Прогон одного канала, дошедший до конца, сообщает об успехе."""
    ingestion = _Ingestion()
    bot = _wire(await make_bot(), ingestion)

    assert await bot.poll_channel_now(7) == "ok"
    assert ingestion.channel_calls == [7]
    assert bot._current_poll_task is None


async def test_a_channel_the_pipeline_could_not_take_reports_missing(make_bot):
    """Канал, который конвейер не взял, отдаёт «не найден».

    Так окно скажет про удалённую строку или канал без имени по-своему,
    а не общей «ошибкой».
    """
    bot = _wire(await make_bot(), _Ingestion(outcome=False))

    assert await bot.poll_channel_now(7) == "missing"


async def test_a_manual_channel_poll_while_busy_is_refused(make_bot):
    """Второй прогон при занятом месте отказывается, а не встаёт рядом.

    Два цикла разом дерутся за кэш векторов и курсор канала.
    """
    ingestion = _Ingestion()
    bot = _wire(await make_bot(), ingestion)
    bot._current_poll_task = asyncio.create_task(asyncio.sleep(30))

    assert await bot.poll_channel_now(7) == "busy"
    assert ingestion.channel_calls == []

    bot._current_poll_task.cancel()


async def test_a_cancelled_channel_poll_frees_the_slot(make_bot):
    """Отменённый прогон освобождает место и сообщает об отмене.

    Не освободив, кнопка «прогнать» замерла бы навсегда: занятость
    проверяется по тому же полю.
    """
    bot = _wire(await make_bot(), _Ingestion(hangs=True))
    running = asyncio.create_task(bot.poll_channel_now(7))
    await asyncio.sleep(0)
    bot.cancel_current_poll()

    assert await running == "cancelled"
    assert bot._current_poll_task is None


async def test_a_failed_channel_poll_frees_the_slot_too(make_bot):
    """Сбой прогона тоже освобождает место и сообщает об ошибке."""
    bot = _wire(await make_bot(), _Ingestion(error=RuntimeError("сорвалось")))

    assert await bot.poll_channel_now(7) == "error"
    assert bot._current_poll_task is None


@pytest.mark.parametrize(
    "error",
    [pytest.param(None, id="успех"), pytest.param(RuntimeError("сорвалось"), id="сбой")],
)
async def test_the_window_hears_both_ends_of_a_channel_poll(make_bot, error):
    """Окно узнаёт и о начале, и о конце прогона — чем бы тот ни кончился.

    На оповещении о конце гаснет крутящаяся полоса внизу окна.
    """
    hooks = _Hooks()
    bot = _wire(await make_bot(), _Ingestion(error=error), hooks)

    await bot.poll_channel_now(7)

    assert hooks.log == ["начало", "конец"]


async def test_a_broken_start_hook_does_not_stop_the_poll(make_bot):
    """Сломанное оповещение о начале прогон не отменяет.

    Оно только красит полосу в окне; из-за него не запустить сбор
    вакансий было бы обменом важного на украшение.
    """
    ingestion = _Ingestion()
    bot = _wire(await make_bot(), ingestion, _Hooks(start_error=RuntimeError("окно")))

    assert await bot.poll_channel_now(7) == "ok"
    assert ingestion.channel_calls == [7]


async def test_a_broken_end_hook_does_not_change_the_outcome(make_bot):
    """Сломанное оповещение о конце не меняет исход прогона."""
    bot = _wire(await make_bot(), _Ingestion(), _Hooks(end_error=RuntimeError("окно")))

    assert await bot.poll_channel_now(7) == "ok"
    assert bot._current_poll_task is None


async def test_a_forced_full_poll_reports_success(make_bot):
    """Полный прогон по кнопке обновления доходит до конца и сообщает успех."""
    ingestion = _Ingestion()
    bot = _wire(await make_bot(), ingestion)

    assert await bot.force_poll_once() == "ok"
    assert ingestion.full_calls == 1
    assert bot._current_poll_task is None


async def test_a_forced_full_poll_while_busy_is_refused(make_bot):
    """Полный прогон при занятом месте отказывается."""
    ingestion = _Ingestion()
    bot = _wire(await make_bot(), ingestion)
    bot._current_poll_task = asyncio.create_task(asyncio.sleep(30))

    assert await bot.force_poll_once() == "busy"
    assert ingestion.full_calls == 0

    bot._current_poll_task.cancel()


async def test_a_cancelled_full_poll_frees_the_slot(make_bot):
    """Отменённый полный прогон освобождает место и сообщает об отмене."""
    bot = _wire(await make_bot(), _Ingestion(hangs=True))
    running = asyncio.create_task(bot.force_poll_once())
    await asyncio.sleep(0)
    bot.cancel_current_poll()

    assert await running == "cancelled"
    assert bot._current_poll_task is None


async def test_a_failed_full_poll_frees_the_slot_too(make_bot):
    """Сбой полного прогона тоже освобождает место и сообщает об ошибке."""
    bot = _wire(await make_bot(), _Ingestion(error=RuntimeError("сорвалось")))

    assert await bot.force_poll_once() == "error"
    assert bot._current_poll_task is None


async def test_the_window_hears_both_ends_of_a_full_poll(make_bot):
    """Окно узнаёт и о начале, и о конце полного прогона."""
    hooks = _Hooks()
    bot = _wire(await make_bot(), _Ingestion(), hooks)

    await bot.force_poll_once()

    assert hooks.log == ["начало", "конец"]
