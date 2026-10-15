"""Сессия агента под надзором: срок человека, общий срок, остановка."""

import asyncio

import pytest

from backend.agent.kit import AgentEnd, SessionPlan
from backend.agent.prompts.frame import system_prompt
from backend.agent.sessions import run_guarded
from backend.agent.stops import HumanTimeout
from backend.models import ProfileLanguage
from tests.dbio import put
from tests.factories import profile_row
from tests.fakes.agent import kit_for, silent_gate

PLAN = SessionPlan(system_prompt="", task="", tools=[], web_search=False)


async def test_an_outside_stop_puts_the_session_out_before_returning(make_pipeline):
    started, stopped = asyncio.Event(), asyncio.Event()

    async def session(plan):
        started.set()
        try:
            await asyncio.sleep(3600)
        finally:
            stopped.set()

    guarded = asyncio.create_task(run_guarded(
        kit_for(await make_pipeline(), gate=silent_gate(), run_session=session), PLAN))
    await started.wait()
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


async def test_the_frame_names_the_language_of_the_person(make_pipeline, session_factory):
    """Причины и итоги для человека агент пишет на его языке — первом родном из анкеты."""
    person = profile_row()
    await put(session_factory, person)
    await put(session_factory, ProfileLanguage(profile_id=person.id, language="Қазақша", level="native"))
    seen = []

    async def session(plan):
        seen.append(plan.system_prompt)
        return AgentEnd(True, "", False)

    plan = SessionPlan(system_prompt=system_prompt("РОЛЬ", []), task="", tools=[], web_search=False)
    await run_guarded(kit_for(await make_pipeline(), gate=silent_gate(), run_session=session), plan)

    assert "на языке пользователя — Қазақша" in seen[0]
