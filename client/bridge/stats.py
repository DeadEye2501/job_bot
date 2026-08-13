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

    @Slot(str)
    def request_stats_kpi(self, period: str) -> None:
        """Top-row KPIs для экрана Statistics. period ∈
        {today, week, month, quarter, all}.
        """
        async def run() -> str:
            async with self._session_factory() as session:
                data = await stats_summary.get_stats_kpi(session, period=period)
            return _ok(data)

        self._dispatch(self.stats_kpi_loaded, run())

    @Slot(str)
    def request_stats_status_breakdown(self, period: str) -> None:
        """Counts по 11 статусам за period — для funnel и all-status
        счётчиков. Echoes period для drop'а stale-ответов.
        """
        async def run() -> str:
            async with self._session_factory() as session:
                data = await stats_summary.get_stats_status_breakdown(
                    session, period=period,
                )
            return _ok(data)

        self._dispatch(self.stats_status_breakdown_loaded, run())

    @Slot(str)
    def request_stats_hr_responses(self, period: str) -> None:
        """HR-response-time + weekday-распределение. Source:
        VacancyStatusHistory (Applied) + Message (incoming) — см.
        get_stats_hr_responses в repository."""
        async def run() -> str:
            async with self._session_factory() as session:
                data = await stats_summary.get_stats_hr_responses(
                    session, period=period,
                )
            return _ok(data)

        self._dispatch(self.stats_hr_responses_loaded, run())

    @Slot(str)
    def request_stats_skills(self, period: str) -> None:
        """Top-N skills (vacancy.stack tags за period) + флаг mine."""
        async def run() -> str:
            async with self._session_factory() as session:
                data = await stats_summary.get_stats_skills(
                    session, period=period,
                )
            return _ok(data)

        self._dispatch(self.stats_skills_loaded, run())

    @Slot(str)
    def request_stats_channels_pipeline(self, period: str) -> None:
        """Per-channel pipeline (Ингест / Воронка отклика / Конверсия)."""
        async def run() -> str:
            async with self._session_factory() as session:
                data = await stats_pipeline.get_stats_channels_pipeline(
                    session, period=period,
                )
            return _ok(data)

        self._dispatch(self.stats_channels_pipeline_loaded, run())
