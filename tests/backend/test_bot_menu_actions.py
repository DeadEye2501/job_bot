"""Следствия команд из меню карточки вакансии.

Повторный прогон одной вакансии занимает то же единственное место, что и
обычный цикл: пользователь получает привычную полосу внизу окна и ту же
кнопку «остановить». Отказ по занятости здесь отличается от неудачи прогона
только на словах — окно и в том, и в другом случае показывает подсказку.

Отправка отклика ничего вокруг себя не занимает: она короткая, а её итог
конвейер сам объясняет словами, которые окно показывает как есть.
"""

import asyncio

import pytest

from tests.fakes.ingestion import FakeIngestion, WindowHooks, wire


async def test_a_rerun_reaches_the_pipeline_and_frees_the_slot(make_bot):
    """Повторный прогон доходит до конвейера и освобождает место."""
    ingestion = FakeIngestion()
    bot = wire(await make_bot(), ingestion)

    assert await bot.ui_rerun_vacancy_pipeline(5) is True
    assert ingestion.rerun_calls == [5]
    assert bot._current_poll_task is None


async def test_a_rerun_the_pipeline_refused_reports_failure(make_bot):
    """Прогон, за который конвейер не взялся, сообщает о неудаче."""
    bot = wire(await make_bot(), FakeIngestion(outcome=False))

    assert await bot.ui_rerun_vacancy_pipeline(5) is False


async def test_a_rerun_while_busy_is_refused(make_bot, busy_slot):
    """Повторный прогон при занятом месте не запускается.

    Иначе он и идущий цикл разошлись бы по одному и тому же кэшу
    векторов.
    """
    ingestion = FakeIngestion()
    bot = wire(await make_bot(), ingestion)
    busy_slot(bot)

    assert await bot.ui_rerun_vacancy_pipeline(5) is False
    assert ingestion.rerun_calls == []



async def test_a_cancelled_rerun_frees_the_slot(make_bot):
    """Отменённый повторный прогон освобождает место и сообщает о неудаче."""
    bot = wire(await make_bot(), FakeIngestion(hangs=True))
    running = asyncio.create_task(bot.ui_rerun_vacancy_pipeline(5))
    await asyncio.sleep(0)
    bot.cancel_current_poll()

    assert await running is False
    assert bot._current_poll_task is None


async def test_a_failed_rerun_frees_the_slot_too(make_bot):
    """Сбой повторного прогона тоже освобождает место."""
    bot = wire(await make_bot(), FakeIngestion(error=RuntimeError("сорвалось")))

    assert await bot.ui_rerun_vacancy_pipeline(5) is False
    assert bot._current_poll_task is None


async def test_a_rerun_tells_the_window_which_vacancy_it_took(make_bot):
    """Окно узнаёт, за какую именно вакансию взялись.

    Долю сделанного посчитать нечем — вакансия одна, — поэтому обе
    границы нулевые, а несёт строку название.
    """
    hooks = WindowHooks()
    bot = wire(await make_bot(), FakeIngestion(), hooks)

    await bot.ui_rerun_vacancy_pipeline(5)

    assert hooks.log == ["начало", "конец"]
    assert hooks.progress == [("rerun", "Прогон вакансии #5…", 0, 0)]


@pytest.mark.parametrize(
    "broken",
    [
        pytest.param("start_error", id="начало"),
        pytest.param("progress_error", id="доля"),
        pytest.param("end_error", id="конец"),
    ],
)
async def test_a_broken_window_hook_does_not_stop_a_rerun(make_bot, broken):
    """Сломанное оповещение окна повторный прогон не отменяет.

    Оповещения красят полосу внизу; менять из-за них исход работы значило
    бы отдавать нужное за украшение.
    """
    ingestion = FakeIngestion()
    hooks = WindowHooks(**{broken: RuntimeError("окно")})
    bot = wire(await make_bot(), ingestion, hooks)

    assert await bot.ui_rerun_vacancy_pipeline(5) is True
    assert ingestion.rerun_calls == [5]


async def test_sending_an_application_passes_the_pipeline_answer_through(make_bot):
    """Итог отправки отклика передаётся окну как есть.

    Причину неудачи составляет конвейер: окно показывает её словами, а
    не переводит код обратно в текст.
    """
    ingestion = FakeIngestion(outcome=(False, "HR без адреса"))
    bot = wire(await make_bot(), ingestion)

    assert await bot.ui_send_vacancy_application(5) == (False, "HR без адреса")
    assert ingestion.application_calls == [5]


async def test_sending_an_application_does_not_take_the_poll_slot(make_bot, busy_slot):
    """Отправка отклика место прогона не занимает.

    Она короткая, и занимать ею место значило бы гасить кнопку
    «прогнать» на время одного сообщения.
    """
    bot = wire(await make_bot(), FakeIngestion(outcome=(True, "ок")))
    busy_slot(bot)

    assert await bot.ui_send_vacancy_application(5) == (True, "ок")

