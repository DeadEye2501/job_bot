"""Набор сессии агента без браузера, водителя и человека."""

from datetime import date

from backend.agent.kit import AgentKit

TODAY = date(2026, 10, 9)


def tool(tools, name):
    """Инструмент по имени — так его видит агент."""
    return next(t for t in tools if t.__name__ == name)


def kit_for(pipeline, *, browser=None, gate=None, run_session=None) -> AgentKit:
    return AgentKit(pipeline=pipeline, browser=browser, gate=gate,
                    run_session=run_session, today=TODAY)
