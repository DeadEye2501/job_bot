"""Набор сессии агента без браузера, водителя и человека."""

from datetime import date

from backend.agent.jobs import ApplyJob
from backend.agent.kit import AgentKit

TODAY = date(2026, 10, 9)


def tool(tools, name):
    """Инструмент по имени — так его видит агент."""
    return next(t for t in tools if t.__name__ == name)


def apply_job(vacancy_id: int, **overrides) -> ApplyJob:
    """Задание откликателя: по умолчанию форма работодателя, без агрегатора, всерьёз."""
    fields = dict(vacancy_id=vacancy_id, method="form", target="https://company.test/apply",
                  aggregator_id=None, profile_id=1, forced=False, simulated=False,
                  letter_writer="app")
    fields.update(overrides)
    return ApplyJob(**fields)


def kit_for(pipeline, *, browser=None, gate=None, run_session=None) -> AgentKit:
    return AgentKit(pipeline=pipeline, browser=browser, gate=gate,
                    run_session=run_session, today=TODAY)
