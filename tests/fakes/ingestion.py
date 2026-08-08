"""Подделка конвейера сбора и оповещений окна о ходе цикла.

Настоящий конвейер ходит в Telegram и в языковую модель. Боту от него нужно
одно: чем кончился прогон. Подделка это и сообщает, попутно считая заходы —
по ним видно, отказал ли бот в повторном прогоне или всё-таки запустил его.
"""

import asyncio


class FakeIngestion:
    """Сообщает, чем кончился прогон, и записывает, о чём его просили."""

    def __init__(self, *, outcome=True, error=None, hangs=False) -> None:
        self._outcome = outcome
        self._error = error
        self._hangs = hangs
        self.channel_calls: list[int] = []
        self.rerun_calls: list[int] = []
        self.application_calls: list[int] = []
        self.full_calls = 0

    async def poll_one_channel(self, channel_id: int):
        self.channel_calls.append(channel_id)
        return await self._answer()

    async def poll_active_channels(self):
        self.full_calls += 1
        return await self._answer()

    async def rerun_pipeline_for_vacancy(self, vacancy_id: int):
        self.rerun_calls.append(vacancy_id)
        return await self._answer()

    async def send_application_for_vacancy(self, vacancy_id: int):
        self.application_calls.append(vacancy_id)
        return await self._answer()

    async def _answer(self):
        if self._hangs:
            await asyncio.sleep(30)
        if self._error is not None:
            raise self._error
        return self._outcome


class WindowHooks:
    """Оповещения окна о ходе цикла: начало, конец и доля сделанного."""

    def __init__(self, *, start_error=None, end_error=None, progress_error=None) -> None:
        self._start_error = start_error
        self._end_error = end_error
        self._progress_error = progress_error
        self.log: list[str] = []
        self.progress: list[tuple] = []

    def start(self) -> None:
        self.log.append("начало")
        if self._start_error is not None:
            raise self._start_error

    def end(self) -> None:
        self.log.append("конец")
        if self._end_error is not None:
            raise self._end_error

    def on_progress(self, stage, label, current, total) -> None:
        self.progress.append((stage, label, current, total))
        if self._progress_error is not None:
            raise self._progress_error


def wire(bot, ingestion, hooks=None):
    """Ставит боту подставной конвейер и подключает оповещения окна."""
    bot._ingestion = ingestion
    if hooks is not None:
        bot.on_cycle_start = hooks.start
        bot.on_cycle_end = hooks.end
        bot.on_progress = hooks.on_progress
    return bot
