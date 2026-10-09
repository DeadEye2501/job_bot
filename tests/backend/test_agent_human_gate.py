"""Пауза на человека: браузер виден, окно знает, срок — час."""

import asyncio

from backend.agent.human_gate import HumanGate
from tests.fakes.browser import FakeBrowser


def _gate(limit=60.0):
    told = []
    gate = HumanGate(lambda kind, host: told.append((kind, host)),
                     lambda: told.append("resolved"), limit_sec=limit)
    return gate, told


async def test_ready_lets_the_agent_go_on():
    gate, told = _gate()
    browser = FakeBrowser()
    waiting = asyncio.create_task(gate.wait("captcha", "site.test", browser))
    await asyncio.sleep(0)

    gate.resolve()

    assert await waiting == "готово"
    assert told == [("captcha", "site.test"), "resolved"]
    assert browser.calls == ["show", "hide"]


async def test_the_deadline_raises_the_flag_for_the_round():
    gate, _ = _gate(limit=0.01)

    assert (await gate.wait("login", "site.test", FakeBrowser())).startswith("срок вышел")
    assert gate.expired.is_set()


async def test_a_repeated_call_waits_on_the_same_deadline():
    """Водитель оборвал долгий вызов — повтор ждёт того же «Готово», а не заново час."""
    gate, told = _gate(limit=0.05)
    first = asyncio.create_task(gate.wait("captcha", "site.test", FakeBrowser()))
    await asyncio.sleep(0.03)
    first.cancel()

    assert (await gate.wait("captcha", "site.test", FakeBrowser())).startswith("срок вышел")
    assert told.count(("captcha", "site.test")) == 1


async def test_a_stop_releases_the_waiting_call_at_once():
    gate, _ = _gate(limit=3600)
    waiting = asyncio.create_task(gate.wait("captcha", "site.test", FakeBrowser()))
    await asyncio.sleep(0)

    gate.abort()

    assert (await asyncio.wait_for(waiting, 1)).startswith("обход остановлен")


async def test_a_stop_before_the_call_is_not_lost():
    """Остановили, пока агент ничего не ждал, — его следующий зов не держит место прогона час."""
    gate, told = _gate(limit=3600)
    gate.abort()

    answer = await asyncio.wait_for(gate.wait("captcha", "site.test", FakeBrowser()), 1)

    assert answer.startswith("обход остановлен")
    assert told == []
