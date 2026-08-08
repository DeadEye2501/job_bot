"""Следствия гашения отложенных разборов при остановке и выключении.

Отложенный разбор переживает того, кто его завёл: таймер сидит на паузе и
через минуту полезет в базу и в языковую модель. Поэтому при остановке его
гасят — иначе он придёт в уже закрытые соединения.

Выключение бота отличается: соединения ещё живы, и накопленное сливают —
разбирают начисто. Иначе очередь, набранная за минуту до нажатия «выключить»,
пропадала бы молча, и пользователь видел бы ответ HR в переписке при
нетронутом статусе вакансии.
"""

from backend.flows import dm_classify
import asyncio
from contextlib import suppress


async def test_stopping_puts_out_the_pending_timers(dm_pipeline):
    """Остановка гасит взведённые таймеры.

    Через минуту такой таймер полез бы в базу и в языковую модель, а к
    этому времени соединения уже закрыты.
    """
    dm_pipeline.schedule_dm_classification(7, 1, 10, "привет")
    timer = dm_pipeline._dm_classify_tasks[7]

    await dm_pipeline.cancel_pending_dm_classifications()

    assert timer.done()
    assert dm_pipeline._dm_classify_tasks == {}


async def test_stopping_reads_nothing(dm_pipeline):
    """Остановка накопленное не разбирает: соединения уже закрываются."""
    dm_pipeline.schedule_dm_classification(7, 1, 10, "привет")

    await dm_pipeline.cancel_pending_dm_classifications()

    assert dm_pipeline.classified == []
    assert dm_pipeline._dm_classify_buffer == {}


async def test_switching_off_reads_what_was_collected(dm_pipeline):
    """Выключение разбирает накопленное начисто.

    Соединения ещё живы. Молча выбросив очередь, набранную за минуту до
    нажатия, пользователю показали бы ответ HR при нетронутом статусе.
    """
    dm_pipeline.schedule_dm_classification(7, 1, 10, "привет")

    await dm_pipeline.cancel_pending_dm_classifications(drain=True)

    assert [hr_id for hr_id, _ in dm_pipeline.classified] == [7]
    assert dm_pipeline._dm_classify_buffer == {}


async def test_switching_off_reads_every_correspondent(dm_pipeline):
    """Выключение разбирает всех накопленных, а не первого попавшегося."""
    dm_pipeline.schedule_dm_classification(7, 1, 10, "от первого")
    dm_pipeline.schedule_dm_classification(8, 2, 20, "от второго")

    await dm_pipeline.cancel_pending_dm_classifications(drain=True)

    assert sorted(hr_id for hr_id, _ in dm_pipeline.classified) == [7, 8]


async def test_one_broken_reading_does_not_stop_the_others(monkeypatch, dm_pipeline):
    """Сорвавшийся разбор одного собеседника не отменяет разбор остальных.

    Слив идёт при выключении и разом по всем: уронив его на первом, бот
    потерял бы очереди всех прочих.
    """
    dm_pipeline.schedule_dm_classification(7, 1, 10, "от первого")
    dm_pipeline.schedule_dm_classification(8, 2, 20, "от второго")
    good: list[int] = []

    async def classify(pipeline, hr_id):
        if hr_id == 7:
            raise RuntimeError("модель не ответила")
        good.append(hr_id)

    monkeypatch.setattr(dm_classify, "classify_and_apply_for_hr", classify)

    await dm_pipeline.cancel_pending_dm_classifications(drain=True)

    assert good == [8]


async def test_an_empty_buffer_is_not_read(dm_pipeline):
    """Пустой накопитель не разбирается.

    Обращение к модели с пустым пакетом — деньги и секунды за ответ ни о
    чём.
    """
    dm_pipeline.schedule_dm_classification(7, 1, 10, "привет")
    dm_pipeline.remove_dm_buffer_msg(7, 10)

    await dm_pipeline.cancel_pending_dm_classifications(drain=True)

    assert dm_pipeline.classified == []


async def test_a_stopping_bot_ignores_the_request_to_read(dm_pipeline):
    """У останавливающегося бота просьба разобрать не исполняется.

    Признак остановки перевешивает: соединения уже закрываются, и разбор
    пошёл бы в закрытое.
    """
    dm_pipeline.schedule_dm_classification(7, 1, 10, "привет")
    dm_pipeline.mark_shutting_down()

    await dm_pipeline.cancel_pending_dm_classifications(drain=True)

    assert dm_pipeline.classified == []
    assert dm_pipeline._dm_classify_buffer == {}


async def test_a_reading_already_under_way_is_not_waited_for_at_all(monkeypatch, dm_pipeline):
    """Начавшийся разбор остановка не дожидается вовсе.

    Ожидание в пять секунд заведено именно ради него: отмена — только
    просьба, и разбор, уже прошедший таймер, её не заметит. Но ждут там
    лишь тех, кто числится в списке таймеров, а разбор вычёркивает себя
    оттуда прямо перед началом. Дождаться его поэтому невозможно, и он
    продолжает работать после того, как остановка вернула управление, —
    ровно то, от чего ожидание должно было уберечь.

    Тест закрепляет сегодняшнее поведение: при починке он покраснеет.
    """
    dm_pipeline.DM_CLASSIFY_DEBOUNCE_SEC = 0
    started = asyncio.Event()

    async def hangs(pipeline, hr_id):
        started.set()
        await asyncio.sleep(30)

    monkeypatch.setattr(dm_classify, "classify_and_apply_for_hr", hangs)
    dm_pipeline.schedule_dm_classification(7, 1, 10, "привет")
    running = dm_pipeline._dm_classify_tasks[7]
    await started.wait()

    await dm_pipeline.cancel_pending_dm_classifications()

    assert dm_pipeline._dm_classify_tasks == {}
    assert not running.done()

    running.cancel()
    with suppress(asyncio.CancelledError):
        await running


async def test_nothing_pending_means_nothing_to_wait_for(dm_pipeline):
    """Когда гасить нечего, остановка ничего не ждёт и не падает."""
    await dm_pipeline.cancel_pending_dm_classifications()

    assert dm_pipeline._dm_classify_tasks == {}
