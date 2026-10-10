"""Пауза на человека: браузер виден, окно знает, срок — час."""

import asyncio

import pytest

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


async def test_a_window_that_failed_to_show_is_shown_on_the_next_call():
    """Не показанный браузер — не начатое ожидание: следующий зов показывает его и зовёт человека."""
    gate, told = _gate()
    broken = FakeBrowser()

    async def refuse():
        raise RuntimeError("браузер не поднялся")

    broken.show = refuse
    with pytest.raises(RuntimeError):
        await gate.wait("captcha", "site.test", broken)
    browser = FakeBrowser()
    waiting = asyncio.create_task(gate.wait("captcha", "site.test", browser))
    await asyncio.sleep(0)
    gate.resolve()

    assert await waiting == "готово"
    assert told == [("captcha", "site.test"), "resolved"]
    assert browser.calls == ["show", "hide"]


async def test_a_stop_while_the_window_comes_up_is_not_a_wait():
    """Обход остановили, пока браузер поднимался: ждать нечего и звать человека незачем."""
    gate, told = _gate()
    browser = FakeBrowser()
    rising = asyncio.Event()

    async def slow_show():
        rising.set()
        await asyncio.sleep(0.01)

    browser.show = slow_show
    waiting = asyncio.create_task(gate.wait("captcha", "site.test", browser))
    await rising.wait()

    gate.abort()

    assert (await asyncio.wait_for(waiting, 1)).startswith("обход остановлен")
    assert told == []


async def test_a_click_on_the_plate_brings_the_waiting_browser_forward_again():
    """Человек свернул браузер или ушёл в приложение — нажатие на плашку выводит его снова."""
    gate, _ = _gate()
    browser = FakeBrowser()
    waiting = asyncio.create_task(gate.wait("captcha", "site.test", browser))
    await asyncio.sleep(0)

    gate.reveal()
    await asyncio.sleep(0)
    gate.resolve()
    await waiting

    assert browser.calls == ["show", "show", "hide"]


async def test_a_click_when_nobody_waits_shows_nothing():
    """Ожидание кончилось — браузер принадлежит уже следующему шагу агента, и трогать его незачем."""
    gate, _ = _gate()
    browser = FakeBrowser()
    waiting = asyncio.create_task(gate.wait("captcha", "site.test", browser))
    await asyncio.sleep(0)
    gate.resolve()
    await waiting

    gate.reveal()
    await asyncio.sleep(0)

    assert browser.calls == ["show", "hide"]


async def test_a_click_right_before_the_check_still_sends_the_browser_back():
    """Нажали на плашку и сразу на галочку — браузер уходит назад, а не остаётся поверх приложения."""
    gate, _ = _gate()
    browser = FakeBrowser()
    waiting = asyncio.create_task(gate.wait("captcha", "site.test", browser))
    await asyncio.sleep(0)

    async def slow_show():
        await asyncio.sleep(0.01)
        browser.calls.append("show")

    browser.show = slow_show
    gate.reveal()
    gate.resolve()
    await waiting

    assert browser.calls == ["show", "show", "hide"]


async def test_a_click_after_the_wait_expired_does_not_raise_a_browser():
    """Срок вышел, работа агента кончается и закрывает браузер: поднятый нажатием заново, он
    занял бы профиль сайта, и никто бы его не закрыл."""
    gate, _ = _gate(limit=0.01)
    browser = FakeBrowser()
    await gate.wait("captcha", "site.test", browser)

    gate.reveal()
    await asyncio.sleep(0)

    assert browser.calls == ["show"]
