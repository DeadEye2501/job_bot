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

    assert await bot.ui_rerun_vacancy_pipeline(5) == "ok"
    assert ingestion.rerun_calls == [5]
    assert bot.current_poll_task is None


async def test_pasted_text_reaches_the_pipeline_and_frees_the_slot(make_bot):
    """Вставленный текст доходит до конвейера, называет себя и освобождает место.

    Место прогона одно на всех, и не освободи его приём — кнопка сбора и
    прогон вакансии замерли бы навсегда: занятость читается по тому же полю.
    Имя ступени окно ловит по строке: опечатайся она здесь, человек увидел бы
    внизу две пустые полосы без единого слова о том, что идёт.
    """
    ingestion = FakeIngestion()
    hooks = WindowHooks()
    bot = wire(await make_bot(), ingestion, hooks)

    assert await bot.ui_ingest_pasted_text("Ищем повара", None) == "ok"
    assert ingestion.pasted_calls == [("Ищем повара", None)]
    assert hooks.progress == [("pasted", "Разбор вставленного объявления…", 0, 0)]
    assert bot.current_poll_task is None


async def test_the_word_of_the_pasted_intake_reaches_the_window_as_it_is(make_bot):
    """Слово приёма доезжает до окна как есть.

    Повтор, молчащая модель отпечатков и не дошедший разбор — три разные
    беды, и человеку про них говорят разное; сведи их к одному «не вышло», и
    он не узнает, что вакансия давно в списке.
    """
    bot = wire(await make_bot(), FakeIngestion(word_outcome="duplicate"))

    assert await bot.ui_ingest_pasted_text("Ищем повара", None) == "duplicate"


async def test_a_paste_while_the_slot_is_busy_is_refused_without_calling_the_pipeline(
    make_bot, busy_slot
):
    """Занятое место отбивает приём, не начиная работы.

    Два прогона разом подрались бы за кэш отпечатков: первый пишет в него
    заведённое, второй сверяется с ним же.
    """
    ingestion = FakeIngestion()
    bot = wire(await make_bot(), ingestion)
    busy_slot(bot)

    assert await bot.ui_ingest_pasted_text("Ищем повара", None) == "busy"
    assert ingestion.pasted_calls == []


async def test_a_delete_from_the_window_reaches_the_pipeline(make_bot):
    """Удаление по кнопке из окна доходит до конвейера, а не до репозитория.

    Мимо конвейера строка исчезла бы, а её вектор остался в кэше отсева
    перепостов — и следующее похожее объявление молча отсеклось бы как повтор
    того, чего больше нет.
    """
    ingestion = FakeIngestion()
    bot = wire(await make_bot(), ingestion)

    assert await bot.ui_forget_vacancy(5) is True
    assert ingestion.forget_calls == [5]


async def test_a_delete_of_a_gone_vacancy_reports_failure(make_bot):
    """Удаление строки, которой уже нет, отвечает окну отказом.

    По этому ответу окно говорит «вакансия не найдена»: строку мог убрать
    другой экран или сам конвейер, пока карточка была открыта.
    """
    bot = wire(await make_bot(), FakeIngestion(outcome=False))

    assert await bot.ui_forget_vacancy(5) is False


async def test_a_rerun_the_pipeline_refused_reports_its_own_word(make_bot):
    """Слово конвейера доезжает до окна как есть.

    Молчащая модель и снесённая вакансия — разные беды, и говорят о них
    разное; свести их к одному «не вышло» значило бы послать человека искать
    запись, которая на месте.
    """
    bot = wire(await make_bot(), FakeIngestion(word_outcome="llm"))

    assert await bot.ui_rerun_vacancy_pipeline(5) == "llm"


async def test_a_rerun_while_busy_is_refused(make_bot, busy_slot):
    """Повторный прогон при занятом месте не запускается.

    Иначе он и идущий цикл разошлись бы по одному и тому же кэшу
    векторов.
    """
    ingestion = FakeIngestion()
    bot = wire(await make_bot(), ingestion)
    busy_slot(bot)

    assert await bot.ui_rerun_vacancy_pipeline(5) == "busy"
    assert ingestion.rerun_calls == []



async def test_a_cancelled_rerun_frees_the_slot(make_bot):
    """Отменённый повторный прогон освобождает место и сообщает о неудаче."""
    bot = wire(await make_bot(), FakeIngestion(hangs=True))
    running = asyncio.create_task(bot.ui_rerun_vacancy_pipeline(5))
    await asyncio.sleep(0)
    bot.cancel_current_poll()

    assert await running == "cancelled"
    assert bot.current_poll_task is None


async def test_a_failed_rerun_frees_the_slot_too(make_bot):
    """Сбой повторного прогона тоже освобождает место."""
    bot = wire(await make_bot(), FakeIngestion(error=RuntimeError("сорвалось")))

    assert await bot.ui_rerun_vacancy_pipeline(5) == "error"
    assert bot.current_poll_task is None


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

    assert await bot.ui_rerun_vacancy_pipeline(5) == "ok"
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

