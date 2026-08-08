"""Следствия догона переписок по всем HR разом.

Переписок бывает несколько сотен. Идти по ним подряд — это столько же
последовательных обращений к Telegram и заметное ожидание при каждом
включении бота; идти по всем разом — верный способ упереться в предел частоты.
Поэтому они делятся на пачки: внутри пачки параллельно, между пачками пауза.

Сорвавшаяся переписка соседей не роняет: догон идёт один раз при переходе в
рабочий режим, и потерять из-за одной все остальные значило бы оставить
пользователя с половиной разговоров.
"""

import asyncio

from backend.flows.dm import _DM_CATCHUP_BATCH_SIZE, catch_up_missed_dms
from backend.models import HR
from tests.dbio import all_rows, put
from tests.factories import hr_row
from tests.fakes.telegram import FakeTelegramClient


async def _catch_up(session_factory, **kwargs):
    """Догоняет переписки по всем известным HR."""
    await catch_up_missed_dms(
        FakeTelegramClient(), None, "qwen", session_factory, 50, **kwargs
    )


async def _hrs(session_factory, count):
    """Заводит указанное число HR с разными номерами собеседников."""
    await put(
        session_factory,
        *[
            hr_row(name=f"HR {n}", telegram_user_id=700 + n, telegram_username=None)
            for n in range(count)
        ],
    )
    return await all_rows(session_factory, HR)


async def test_every_known_hr_is_caught_up(session_factory, monkeypatch):
    """Догон обходит всех известных HR, а не первого попавшегося."""
    await _hrs(session_factory, 3)
    visited: list[int] = []

    async def backfill(client, hr, *args, **kwargs):
        visited.append(hr.id)

    monkeypatch.setattr("backend.flows.dm.backfill_hr_dm_history", backfill)

    await _catch_up(session_factory)

    assert len(visited) == 3


async def test_an_empty_address_book_is_no_work(session_factory, monkeypatch):
    """Когда HR ещё нет, догон ничего не делает и не падает."""
    visited: list[int] = []

    async def backfill(client, hr, *args, **kwargs):
        visited.append(hr.id)

    monkeypatch.setattr("backend.flows.dm.backfill_hr_dm_history", backfill)

    await _catch_up(session_factory)

    assert visited == []


async def test_a_batch_runs_its_chats_side_by_side(session_factory, monkeypatch):
    """Переписки внутри пачки идут одновременно, а не по очереди.

    Три сотни переписок подряд — это три сотни ожиданий сети, сложенных
    в одно долгое молчание при каждом включении бота.
    """
    await _hrs(session_factory, 3)
    started = 0
    peak = 0

    async def backfill(client, hr, *args, **kwargs):
        nonlocal started, peak
        started += 1
        peak = max(peak, started)
        await asyncio.sleep(0)
        started -= 1

    monkeypatch.setattr("backend.flows.dm.backfill_hr_dm_history", backfill)

    await _catch_up(session_factory)

    assert peak == 3


async def test_batches_are_spaced_out(session_factory, monkeypatch):
    """Между пачками бот выжидает, а не бьёт очередью.

    Пауза даёт пределу частоты выдохнуть; без неё вторая пачка приходит
    ровно в тот миг, когда Telegram уже недоволен первой.
    """
    await _hrs(session_factory, _DM_CATCHUP_BATCH_SIZE + 1)

    async def backfill(client, hr, *args, **kwargs):
        pass

    monkeypatch.setattr("backend.flows.dm.backfill_hr_dm_history", backfill)
    slept: list[float] = []
    real_sleep = asyncio.sleep

    async def note(seconds):
        slept.append(seconds)
        await real_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", note)

    await _catch_up(session_factory)

    assert slept == [1.0]


async def test_the_last_batch_is_not_followed_by_a_pause(
    session_factory, monkeypatch
):
    """После последней пачки бот не ждёт: ждать больше нечего."""
    await _hrs(session_factory, 2)

    async def backfill(client, hr, *args, **kwargs):
        pass

    monkeypatch.setattr("backend.flows.dm.backfill_hr_dm_history", backfill)
    slept: list[float] = []
    real_sleep = asyncio.sleep

    async def note(seconds):
        slept.append(seconds)
        await real_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", note)

    await _catch_up(session_factory)

    assert slept == []


async def test_one_broken_chat_does_not_stop_the_others(
    session_factory, monkeypatch
):
    """Сорвавшаяся переписка соседние не отменяет.

    Догон идёт один раз при переходе в рабочий режим; потерять из-за
    одной переписки все остальные значило бы оставить пользователя с
    половиной разговоров до следующего включения.
    """
    hrs = await _hrs(session_factory, 3)
    done: list[int] = []

    async def backfill(client, hr, *args, **kwargs):
        if hr.id == hrs[0].id:
            raise OSError("сеть")
        done.append(hr.id)

    monkeypatch.setattr("backend.flows.dm.backfill_hr_dm_history", backfill)

    await _catch_up(session_factory)

    assert sorted(done) == sorted(h.id for h in hrs[1:])


async def test_the_window_hooks_reach_every_chat(session_factory, monkeypatch):
    """Оповещения окна доходят до догона каждой переписки.

    Их передают вниз, а не держат наверху: переписка дорисовывается в
    открытой вкладке по мере того, как её строки ложатся в базу.
    """
    await _hrs(session_factory, 2)
    got: list[dict] = []

    async def backfill(client, hr, *args, **kwargs):
        got.append(kwargs)

    monkeypatch.setattr("backend.flows.dm.backfill_hr_dm_history", backfill)
    heard: list[str] = []

    await _catch_up(
        session_factory,
        on_message_persisted=lambda hr_id: heard.append("переписка"),
        on_vacancies_changed=lambda: heard.append("вакансии"),
        schedule_classification=lambda *args: heard.append("разбор"),
    )

    assert len(got) == 2
    for kwargs in got:
        kwargs["on_message_persisted"](1)
        kwargs["on_vacancies_changed"]()
        kwargs["schedule_classification"]()
    assert heard.count("переписка") == 2
    assert heard.count("вакансии") == 2
    assert heard.count("разбор") == 2
