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
import logging

from backend.flows.dm_backfill import _DM_CATCHUP_BATCH_SIZE, DmHooks
from tests.backend.fixtures.backfill import catch_up_everyone
from backend.domain.telegram_identity import DialogPeer
from backend.models import HR
from tests.dbio import all_rows, put
from tests.factories import hr_row
from tests.fakes.telegram import FakeTelegramClient


async def _catch_up(session_factory, **kwargs):
    """Догоняет переписки по всем известным HR."""
    await catch_up_everyone(FakeTelegramClient(), session_factory, **kwargs)


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
    """Догон обходит всех известных HR, а не первого попавшегося.

    Сверяется список посещённых, а не его длина: по длине трёхкратный заход к
    одному собеседнику выглядит так же, как обход троих.
    """
    hrs = await _hrs(session_factory, 3)
    visited: list[int] = []

    async def backfill(hr, *args, **kwargs):
        visited.append(hr.id)

    monkeypatch.setattr("backend.flows.dm_backfill.backfill_hr_dm_history", backfill)

    await _catch_up(session_factory)

    assert sorted(visited) == sorted(hr.id for hr in hrs)


async def test_an_empty_address_book_is_no_work(session_factory, monkeypatch):
    """Когда HR ещё нет, догон ничего не делает и не падает."""
    visited: list[int] = []

    async def backfill(hr, *args, **kwargs):
        visited.append(hr.id)

    monkeypatch.setattr("backend.flows.dm_backfill.backfill_hr_dm_history", backfill)

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

    async def backfill(hr, *args, **kwargs):
        nonlocal started, peak
        started += 1
        peak = max(peak, started)
        await asyncio.sleep(0)
        started -= 1

    monkeypatch.setattr("backend.flows.dm_backfill.backfill_hr_dm_history", backfill)

    await _catch_up(session_factory)

    assert peak == 3


async def test_batches_are_spaced_out(session_factory, monkeypatch):
    """Между пачками бот выжидает, а не бьёт очередью.

    Пауза даёт пределу частоты выдохнуть; без неё вторая пачка приходит
    ровно в тот миг, когда Telegram уже недоволен первой.
    """
    await _hrs(session_factory, _DM_CATCHUP_BATCH_SIZE + 1)

    async def backfill(hr, *args, **kwargs):
        pass

    monkeypatch.setattr("backend.flows.dm_backfill.backfill_hr_dm_history", backfill)
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

    async def backfill(hr, *args, **kwargs):
        pass

    monkeypatch.setattr("backend.flows.dm_backfill.backfill_hr_dm_history", backfill)
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

    async def backfill(hr, *args, **kwargs):
        if hr.id == hrs[0].id:
            raise OSError("сеть")
        done.append(hr.id)

    monkeypatch.setattr("backend.flows.dm_backfill.backfill_hr_dm_history", backfill)

    await _catch_up(session_factory)

    assert sorted(done) == sorted(h.id for h in hrs[1:])


async def test_a_cancelled_chat_leaves_a_trace_and_spares_the_others(
    session_factory, monkeypatch, caplog
):
    """Отменённая переписка попадает в журнал, а соседние догоняются.

    Молчи мы о ней — брошенный проход выглядел бы как удачно законченный, и
    понять по журналу, почему у собеседника пусто, было бы нечем. А гасить
    из-за неё весь догон нельзя: остальные переписки ни при чём.
    """
    hrs = await _hrs(session_factory, 2)
    done: list[int] = []

    async def backfill(hr, *args, **kwargs):
        if hr.id == hrs[0].id:
            raise asyncio.CancelledError
        done.append(hr.id)

    monkeypatch.setattr("backend.flows.dm_backfill.backfill_hr_dm_history", backfill)

    with caplog.at_level(logging.WARNING):
        await _catch_up(session_factory)

    assert done == [hrs[1].id]
    assert "CancelledError" in caplog.text
    # Источником записи стоит догон, а не общий разбор пачек: беду догона
    # человек ищет в журнале под именем догона.
    assert [r.name for r in caplog.records] == ["backend.flows.dm_backfill"]


async def test_the_window_hooks_reach_every_chat(session_factory, monkeypatch):
    """Оповещения окна доходят до догона каждой переписки.

    Их передают вниз, а не держат наверху: переписка дорисовывается в
    открытой вкладке по мере того, как её строки ложатся в базу.
    """
    await _hrs(session_factory, 2)
    got: list[tuple] = []

    async def backfill(hr, dm, hooks, **kwargs):
        got.append((dm, hooks))

    monkeypatch.setattr("backend.flows.dm_backfill.backfill_hr_dm_history", backfill)
    heard: list[str] = []

    await _catch_up(
        session_factory,
        hooks=DmHooks(
            on_message_persisted=lambda hr_id: heard.append("переписка"),
            on_vacancies_changed=lambda: heard.append("вакансии"),
        ),
        schedule_classification=lambda *args: heard.append("разбор"),
    )

    assert len(got) == 2
    for dm, hooks in got:
        hooks.on_message_persisted(1)
        hooks.on_vacancies_changed()
        dm.schedule_classification()
    assert heard.count("переписка") == 2
    assert heard.count("вакансии") == 2
    assert heard.count("разбор") == 2


async def test_only_the_dialogs_are_caught_up_freshest_first(session_factory, monkeypatch):
    """С прочитанным списком переписок догоняются только те, кто в нём есть, —
    свежими вперёд.

    У остальных читать нечего, а попытка уходит в розыск по нику, и на частый
    розыск Telegram отвечает запретом на часы — у новых вакансий перестают
    находиться HR.
    """
    hrs = await _hrs(session_factory, 3)
    visited: list[int] = []

    async def backfill(hr, *args, **kwargs):
        visited.append(hr.id)

    monkeypatch.setattr("backend.flows.dm_backfill.backfill_hr_dm_history", backfill)

    await _catch_up(
        session_factory,
        dialogs=[DialogPeer(hrs[2].telegram_user_id), DialogPeer(hrs[0].telegram_user_id)],
    )

    assert visited == [hrs[2].id, hrs[0].id]


async def test_without_a_dialog_list_everyone_is_caught_up(session_factory, monkeypatch):
    """Список переписок неизвестен — чтение сорвалось или не дошло до конца, —
    обходятся все: считать, что переписок нет, значило бы не догнать ничего."""
    hrs = await _hrs(session_factory, 3)
    visited: list[int] = []

    async def backfill(hr, *args, **kwargs):
        visited.append(hr.id)

    monkeypatch.setattr("backend.flows.dm_backfill.backfill_hr_dm_history", backfill)

    await _catch_up(session_factory, dialogs=None)

    assert sorted(visited) == sorted(hr.id for hr in hrs)

