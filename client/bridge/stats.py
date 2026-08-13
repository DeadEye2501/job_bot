"""Экран «Статистика»: показатели за выбранный срок."""

from __future__ import annotations

from PySide6.QtCore import Signal, Slot

from backend.repository import stats_pipeline, stats_summary
from client.bridge.answer import _ok


class StatsSlots:
    """Пять чтений одной формы: спросили за срок — ответили числами.

    Подмешивающий обязан держать `_session_factory` и `_dispatch`.
    """

    stats_kpi_loaded = Signal(str)
    stats_status_breakdown_loaded = Signal(str)
    stats_hr_responses_loaded = Signal(str)
    stats_skills_loaded = Signal(str)
    stats_channels_pipeline_loaded = Signal(str)

    def _read(self, period: str, reading, signal: Signal) -> None:
        """Спросить показатель за срок и отдать окну.

        Пять чтений экрана различаются только тем, кого спросить и куда
        ответить: ни отбора нагрузки, ни отказов, ни ветвлений у них нет.
        Срок уезжает в репозиторий как есть — незнакомое слово он сводит к
        своему умолчанию сам (`stats_common.stats_period_since`), и второй
        такой же просев на границе разошёлся бы с ним первым же новым сроком.
        """
        async def run() -> str:
            async with self._session_factory() as session:
                return _ok(await reading(session, period=period))

        self._dispatch(signal, run())

    @Slot(str)
    def request_stats_kpi(self, period: str) -> None:
        """Верхний ряд показателей экрана. Срок ∈ {today, week, month,
        quarter, all}.
        """
        self._read(period, stats_summary.get_stats_kpi, self.stats_kpi_loaded)

    @Slot(str)
    def request_stats_status_breakdown(self, period: str) -> None:
        """Счёт по одиннадцати положениям дел — воронка и общие счётчики."""
        self._read(
            period,
            stats_summary.get_stats_status_breakdown,
            self.stats_status_breakdown_loaded,
        )

    @Slot(str)
    def request_stats_hr_responses(self, period: str) -> None:
        """Скорость ответа людей и раскладка по дням недели."""
        self._read(
            period,
            stats_summary.get_stats_hr_responses,
            self.stats_hr_responses_loaded,
        )

    @Slot(str)
    def request_stats_skills(self, period: str) -> None:
        """Самые частые навыки за срок и отметка «есть у меня»."""
        self._read(
            period, stats_summary.get_stats_skills, self.stats_skills_loaded
        )

    @Slot(str)
    def request_stats_channels_pipeline(self, period: str) -> None:
        """Воронка по каналам: сбор, отклики, конверсия."""
        self._read(
            period,
            stats_pipeline.get_stats_channels_pipeline,
            self.stats_channels_pipeline_loaded,
        )
