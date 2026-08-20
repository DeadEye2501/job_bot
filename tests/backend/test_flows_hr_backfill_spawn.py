"""Следствия фонового догона переписки со свежезаведённым HR.

Когда разбор вакансии заводит нового HR, у него в окне пусто — видно только
что отправленный отклик, а прежняя переписка появится в лучшем случае после
перезапуска. Догон запускается фоном именно поэтому: ждать его в разборе
значило бы держать обход канала на времени сетевой загрузки истории и
скачивания вложений.

Задача помнится, пока идёт, и забывается, когда кончилась: остановка бота
гасит по этому списку всё, что ещё работает.
"""

import asyncio
import logging

import pytest

from backend.flows import dm_backfill
from backend.models import HR
from tests.dbio import only_row, put
from tests.factories import hr_row


@pytest.fixture
async def spawning(make_pipeline, session_factory, monkeypatch):
    """Конвейер с подставным догоном и сохранённый HR."""
    await put(session_factory, hr_row(telegram_user_id=777))
    hr = await only_row(session_factory, HR)
    pipeline = await make_pipeline()
    # Крючок окна проставляется опознаваемым: в стенде он пуст, и сверка
    # «доехал ли он до догона» вырождалась бы в `None is None` — заменить
    # проводку пустышкой можно было бы незаметно.
    pipeline.on_new_message = lambda hr_id: None
    pipeline.caught = []
    pipeline.hold = asyncio.Event()
    pipeline.hold.set()

    async def backfill(hr_row_, dm, hooks, **kwargs):
        await pipeline.hold.wait()
        if isinstance(pipeline.caught, Exception):
            raise pipeline.caught
        pipeline.caught.append((hr_row_.id, dm, hooks))

    monkeypatch.setattr("backend.flows.dm_backfill.backfill_hr_dm_history", backfill)
    return pipeline, hr


async def test_the_history_is_caught_up_in_the_background(spawning):
    """Переписка с новым HR догоняется фоном.

    Дождавшись её в разборе, бот держал бы обход канала на времени
    сетевой загрузки истории и скачивания вложений.
    """
    pipeline, hr = spawning

    dm_backfill.spawn_hr_backfill(pipeline, hr)
    assert pipeline.caught == []

    await asyncio.sleep(0)
    assert [hr_id for hr_id, _dm, _hooks in pipeline.caught] == [hr.id]


async def test_the_window_is_wired_to_the_background_catch_up(spawning):
    """Догон получает те же оповещения окна, что и обычный.

    Переписка должна дорисоваться в открытой вкладке сама, без
    перезапуска приложения.
    """
    pipeline, hr = spawning

    dm_backfill.spawn_hr_backfill(pipeline, hr)
    await asyncio.sleep(0)

    _, dm, hooks = pipeline.caught[0]
    assert hooks.on_message_persisted is pipeline.on_new_message
    assert dm.schedule_classification == pipeline.schedule_dm_classification


async def test_a_running_catch_up_is_remembered(spawning):
    """Идущий догон помнится, пока не кончится.

    По этому списку остановка бота гасит всё, что ещё работает: иначе
    задача переживёт его и полезет в закрытые соединения.
    """
    pipeline, hr = spawning
    pipeline.hold = asyncio.Event()

    dm_backfill.spawn_hr_backfill(pipeline, hr)
    await asyncio.sleep(0)

    assert len(pipeline.backfill_tasks) == 1

    pipeline.hold.set()
    await asyncio.sleep(0)


async def test_a_finished_catch_up_is_forgotten(spawning):
    """Законченный догон из списка убирается.

    Иначе список растёт на каждого нового HR и держит завершённые
    задачи до конца работы приложения.
    """
    pipeline, hr = spawning

    dm_backfill.spawn_hr_backfill(pipeline, hr)
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert pipeline.backfill_tasks == set()


async def test_a_broken_catch_up_does_not_surface(spawning, caplog):
    """Сорвавшийся догон наружу не пробивается, а ложится в журнал.

    Он идёт фоном, и некому его поймать: неперехваченная ошибка задачи
    всплыла бы в чужом месте и в чужое время.

    Пустой список задач сам по себе этого не сторожит — он пустеет и без
    всякого перехвата, потому что задача снимается с учёта по завершении в
    любом исходе. Наблюдается поэтому запись с трассировкой: сними перехват —
    и беда осядет в «Task exception was never retrieved», где её не увидит
    ни человек, ни счётчик ошибок в окне.
    """
    pipeline, hr = spawning
    pipeline.caught = RuntimeError("сеть")

    with caplog.at_level(logging.ERROR):
        dm_backfill.spawn_hr_backfill(pipeline, hr)
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    assert pipeline.backfill_tasks == set()
    assert "Traceback (most recent call last)" in caplog.text
    assert "RuntimeError: сеть" in caplog.text


async def test_stopping_the_bot_puts_out_the_catch_up(spawning):
    """Остановка бота гасит незаконченный догон.

    Он ходит в базу и в Telegram; к этому мигу соединения уже
    закрываются.
    """
    pipeline, hr = spawning
    pipeline.hold = asyncio.Event()
    dm_backfill.spawn_hr_backfill(pipeline, hr)
    await asyncio.sleep(0)
    running = next(iter(pipeline.backfill_tasks))

    pipeline.mark_shutting_down()
    await asyncio.sleep(0)

    assert running.cancelled()
