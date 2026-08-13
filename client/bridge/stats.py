"""Экран «Статистика»: показатели за выбранный срок."""

from __future__ import annotations

from backend.repository import stats_pipeline, stats_summary
from client.bridge.answer import reply


class Stats:
    """Пять чтений одной формы: спросили за срок — ответили числами."""

    def __init__(self, runner, session_factory) -> None:
        self._runner = runner
        self._session_factory = session_factory

    def _read(self, period: str, reading) -> dict:
        """Спросить показатель за срок и отдать окну.

        Пять чтений экрана различаются только тем, кого спросить: ни отбора
        нагрузки, ни отказов, ни ветвлений у них нет. Срок уезжает в репозиторий
        как есть — незнакомое слово он сводит к своему умолчанию сам
        (`stats_common.stats_period_since`), и второй такой же просев на границе
        разошёлся бы с ним первым же новым сроком.
        """

        async def run() -> dict:
            async with self._session_factory() as session:
                return await reading(session, period=period)

        return reply(self._runner, run())

    def kpi(self, period: str) -> dict:
        """Верхний ряд показателей экрана. Срок ∈ {today, week, month,
        quarter, all}.
        """
        return self._read(period, stats_summary.get_stats_kpi)

    def status_breakdown(self, period: str) -> dict:
        """Счёт по одиннадцати положениям дел — воронка и общие счётчики."""
        return self._read(period, stats_summary.get_stats_status_breakdown)

    def hr_responses(self, period: str) -> dict:
        """Скорость ответа людей и раскладка по дням недели."""
        return self._read(period, stats_summary.get_stats_hr_responses)

    def skills(self, period: str) -> dict:
        """Самые частые навыки за срок и отметка «есть у меня»."""
        return self._read(period, stats_summary.get_stats_skills)

    def channels_pipeline(self, period: str) -> dict:
        """Воронка по каналам: сбор, отклики, конверсия."""
        return self._read(period, stats_pipeline.get_stats_channels_pipeline)
