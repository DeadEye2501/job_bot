"""Подделка конвейера сбора и оповещений окна о ходе цикла.

Настоящий конвейер ходит в Telegram и в языковую модель. Боту от него нужно
одно: чем кончился прогон. Подделка это и сообщает, попутно считая заходы —
по ним видно, отказал ли бот в повторном прогоне или всё-таки запустил его.
"""

import asyncio

from backend.flows.dm import DmHelpers
from backend.flows.dm_backfill import DmHooks
from backend.flows.pipeline import IngestionPipeline


class FakeIngestion:
    """Сообщает, чем кончился прогон, и записывает, о чём его просили."""

    def __init__(
        self, *, outcome=True, word_outcome="ok", error=None, hangs=False
    ) -> None:
        self._outcome = outcome
        # Прогон канала и прогон вакансии отвечают словом, а не «да/нет»:
        # «нет записи», «канал в отсеве» и «сорвалось» окно называет разным.
        # Поле у них общее — в одной проверке зовут что-то одно.
        self._word_outcome = word_outcome
        self._error = error
        self._hangs = hangs
        self.channel_calls: list[int] = []
        self.rerun_calls: list[int] = []
        self.pasted_calls: list[tuple] = []
        self.forget_calls: list[int] = []
        self.full_calls = 0
        self.buffer_edits: list[tuple] = []
        self.buffer_removals: list[tuple] = []
        self.log: list[str] = []
        self.scheduled: list[tuple] = []
        self.drains = 0
        self.recovery_error: BaseException | None = None
        self.ghosting_error: BaseException | None = None
        self.backfill_tasks: set[asyncio.Task] = set()

    async def recover_orphan_vacancies(self):
        self.log.append("недоразобранные")
        if self.recovery_error is not None:
            raise self.recovery_error

    async def check_ghosting_timeouts(self):
        self.log.append("молчание")
        if self.ghosting_error is not None:
            raise self.ghosting_error

    async def cancel_pending_dm_classifications(self, drain: bool = False):
        self.log.append("слив" if drain else "отмена разбора")
        if drain:
            self.drains += 1

    def mark_shutting_down(self):
        self.log.append("гасим")
        for task in self.backfill_tasks:
            task.cancel()

    def spawn_backfill(self, work, what: str, *, extra: dict | None = None) -> None:
        """Пускает работу задачей и держит на неё ссылку — как настоящий.

        Не зовёт её на месте: тем, что догон **не** дожидается оборота, и
        отличается нынешний цикл от прежнего. Подделка, зовущая работу сразу,
        красила бы эту разницу зелёным при любом исходе.

        Само заведение берётся у настоящего конвейера, а не переписывается:
        из всего конвейера оно трогает один набор задач, который есть и здесь,
        — а переписанное семью строками рядом разъехалось бы с ним первой же
        правкой, и подделка перестала бы вести себя как боевой код ровно там,
        где обещает.
        """
        self.log.append(f"пущено задачей: {what}")
        IngestionPipeline.spawn_backfill(self, work, what, extra=extra)

    def schedule_dm_classification(self, hr_id, *rest):
        self.log.append(f"разбор запланирован: {hr_id}")
        self.scheduled.append((hr_id, *rest))

    def dm_helpers(self) -> DmHelpers:
        """Сотрудники для проводки письма: у подделки все пустые.

        Подделку зовут там, где предмет проверки — сам оборот цикла, а не
        письмо; догон при этом всё равно подменён своим.
        """
        return DmHelpers(session_factory=None)

    def dm_hooks(self) -> DmHooks:
        """Крючки окна: у подделки их нет."""
        return DmHooks()

    def update_dm_buffer_text(self, hr_id: int, tg_message_id: int, text: str) -> None:
        self.buffer_edits.append((hr_id, tg_message_id, text))

    def remove_dm_buffer_msg(self, hr_id: int, tg_message_id: int) -> None:
        self.buffer_removals.append((hr_id, tg_message_id))

    async def poll_one_channel(self, channel_id: int):
        self.channel_calls.append(channel_id)
        return await self._answer(outcome=self._word_outcome)

    async def poll_active_channels(self):
        self.full_calls += 1
        self.log.append("прогон каналов")
        return await self._answer()

    async def rerun_pipeline_for_vacancy(self, vacancy_id: int):
        self.rerun_calls.append(vacancy_id)
        return await self._answer(outcome=self._word_outcome)

    async def ingest_pasted_text(self, text: str, posted_at):
        self.pasted_calls.append((text, posted_at))
        return await self._answer(outcome=self._word_outcome)

    async def forget_vacancy(self, vacancy_id: int):
        self.forget_calls.append(vacancy_id)
        return await self._answer()

    _OWN = object()

    async def _answer(self, *, outcome=_OWN):
        """Ответ подделки: общий или тот, что отвечают словом.

        Часовой, а не `None`: у обхода `None` — такой же осмысленный ответ,
        как и прочие, и проверка «нечего не передали» съела бы его.
        """
        if self._hangs:
            await asyncio.sleep(30)
        if self._error is not None:
            raise self._error
        return self._outcome if outcome is self._OWN else outcome


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
    bot.ingestion = ingestion
    if hooks is not None:
        bot.on_cycle_start = hooks.start
        bot.on_cycle_end = hooks.end
        bot.on_progress = hooks.on_progress
    return bot
