"""Срок сессии агента, ужатый для проверок: его отсчёт видят и сама сессия, и обход."""

import pytest


@pytest.fixture
def short_clock(monkeypatch):
    """Срок сессии в доли секунды и такой же мелкий шаг его отсчёта."""
    monkeypatch.setattr("backend.agent.sessions.SESSION_LIMIT_SEC", 0.05)
    monkeypatch.setattr("backend.agent.sessions._TICK_SEC", 0.01)
