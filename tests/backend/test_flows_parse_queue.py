"""Очередь разбора: найденное агентом разбирается рядом с поиском, по одной."""

from backend.flows.parse_queue import ParseQueue
from tests.backend.fixtures.parse_stub import parse_into


async def test_everything_put_is_parsed_without_a_channel(monkeypatch):
    calls = []
    parse_into(monkeypatch, calls)
    queue = ParseQueue(pipeline=object())

    queue.put(1, "первая")
    queue.put(2, "вторая")
    await queue.drain()

    assert calls == [(1, "первая", None, True), (2, "вторая", None, True)]


async def test_one_broken_parse_does_not_stop_the_rest(monkeypatch):
    calls = []
    parse_into(monkeypatch, calls, fails={1})
    queue = ParseQueue(pipeline=object())

    queue.put(1, "сломается")
    queue.put(2, "разберётся")
    await queue.drain()

    assert [vacancy_id for vacancy_id, *_ in calls] == [2]


async def test_a_stopped_queue_drops_what_is_left(monkeypatch):
    calls = []
    parse_into(monkeypatch, calls)
    queue = ParseQueue(pipeline=object())
    queue.put(1, "x")

    await queue.stop()

    assert calls == []
