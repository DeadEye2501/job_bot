"""Сессия агента под надзором: срок человека, общий срок, остановка."""

import asyncio

import pytest

from backend.agent.kit import AgentEnd, SessionPlan
from backend.agent.sessions import HumanTimeout, run_guarded
from tests.fakes.agent import kit_for, silent_gate

PLAN = SessionPlan(system_prompt="", task="", tools=[], web_search=False)


async def test_an_outside_stop_puts_the_session_out_before_returning(make_pipeline):
    stopped = asyncio.Event()

    async def session(plan):
        try:
            await asyncio.sleep(3600)
        finally:
            stopped.set()

    guarded = asyncio.create_task(run_guarded(
        kit_for(await make_pipeline(), gate=silent_gate(), run_session=session), PLAN))
    await asyncio.sleep(0)
    guarded.cancel()

    with pytest.raises(asyncio.CancelledError):
        await guarded
    assert stopped.is_set()


async def test_an_expired_wait_for_a_person_ends_the_session(make_pipeline):
    gate = silent_gate()

    async def session(plan):
        gate.expired.set()
        await asyncio.sleep(3600)

    with pytest.raises(HumanTimeout):
        await run_guarded(kit_for(await make_pipeline(), gate=gate, run_session=session), PLAN)


async def test_a_session_past_its_limit_is_a_failure(make_pipeline, monkeypatch):
    monkeypatch.setattr("backend.agent.sessions.SESSION_LIMIT_SEC", 0.01)

    async def session(plan):
        await asyncio.sleep(3600)

    end = await run_guarded(kit_for(await make_pipeline(), gate=silent_gate(), run_session=session), PLAN)

    assert end == AgentEnd(False, "сессия агента превысила срок", False)


async def test_a_session_past_its_limit_is_put_out(make_pipeline, monkeypatch):
    """Зависший процесс не переживает обход: просроченная сессия погашена до возврата."""
    monkeypatch.setattr("backend.agent.sessions.SESSION_LIMIT_SEC", 0.01)
    stopped = asyncio.Event()

    async def session(plan):
        try:
            await asyncio.sleep(3600)
        finally:
            stopped.set()

    await run_guarded(kit_for(await make_pipeline(), gate=silent_gate(), run_session=session), PLAN)

    assert stopped.is_set()
