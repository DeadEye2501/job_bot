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

from backend.bot import pasted as pasted_mod
from backend.flows.hand_made import HandRequest
from backend.flows.hand_outcome import HandResult
from tests.fakes.ingestion import FakeIngestion, WindowHooks, wire


async def test_a_rerun_reaches_the_pipeline_and_frees_the_slot(make_bot):
    """Повторный прогон доходит до конвейера и освобождает место."""
    ingestion = FakeIngestion()
    bot = wire(await make_bot(), ingestion)

    assert await bot.ui_rerun_vacancy_pipeline(5) == "ok"
    assert ingestion.rerun_calls == [5]
    assert bot.current_poll_task is None


@pytest.fixture
def requests_seen(monkeypatch):
    """Заявки окна, дошедшие до ручного заведения, и набор агента при каждой."""
    seen = []

    async def ingest_by_hand(kit, request):
        seen.append((kit, request))

    monkeypatch.setattr(pasted_mod.hand_made, "ingest_by_hand", ingest_by_hand)
    return seen


TEXT = HandRequest("text", "Ищем повара", None, False)


async def test_pasted_text_reaches_the_intake_and_frees_the_slot(make_bot, requests_seen):
    """Заявка доходит до ручного заведения с набором агента и освобождает место.

    Место прогона одно на всех, и не освободи его приём — кнопка сбора и
    прогон вакансии замерли бы навсегда: занятость читается по тому же полю.
    """
    bot = wire(await make_bot(), FakeIngestion())

    await bot.ui_ingest_pasted_text(TEXT)

    (kit, request), = requests_seen
    assert kit is not None and request == TEXT
    assert bot.current_poll_task is None


@pytest.mark.parametrize(("url", "kind"), [
    ("https://t.me/pyjobs/5", "post"),
    ("https://telegra.ph/QA-08-21", "article"),
    ("https://t.me/pyjobs", "channel"),
], ids=["пост", "статья", "канал"])
async def test_a_link_is_sorted_once_by_the_bot(make_bot, requests_seen, url, kind):
    """Род ссылки бот решает один раз, и ниже заявка идёт уже своего рода."""
    bot = wire(await make_bot(), FakeIngestion())

    await bot.ui_ingest_pasted_text(HandRequest("link", url, None, True))

    ((_, request),) = requests_seen
    assert request == HandRequest(kind, url, None, True)


async def test_a_page_without_claude_code_is_locked_before_the_slot(make_bot, requests_seen):
    """Страницу читает агент, а без Claude Code его нет: отказ сразу, работа не
    начинается. Пост и статья агента не ждут."""
    bot = wire(await make_bot(), FakeIngestion())

    assert await bot.ui_ingest_pasted_text(HandRequest("link", "https://hh.ru/vacancy/1", None, False)) == "locked"
    assert requests_seen == []


async def test_a_page_with_the_agent_at_hand_goes_through(make_bot, requests_seen, monkeypatch):
    monkeypatch.setattr(pasted_mod, "aggregators_available", lambda bot: None)
    bot = wire(await make_bot(), FakeIngestion())

    await bot.ui_ingest_pasted_text(HandRequest("link", "https://hh.ru/vacancy/1", None, False))

    ((_, request),) = requests_seen
    assert request.tab == "page"


async def test_a_job_that_never_told_the_window_answers_with_its_own_end(make_bot, monkeypatch):
    """Работа сорвалась до итога — окно слышит срыв: другой вести не будет."""
    bot = wire(await make_bot(), FakeIngestion())

    async def broke(kit, request):
        raise RuntimeError("база не отвечает")

    monkeypatch.setattr(pasted_mod.hand_made, "ingest_by_hand", broke)

    assert await bot.ui_ingest_pasted_text(TEXT) == "error"


async def test_the_bot_forwards_the_end_of_an_intake_to_the_window(make_bot):
    """Итог заведения от конвейера доезжает до окна: второй вести по концу
    работы нет, и без этой пересылки окно ждало бы итога вечно."""
    bot = await make_bot()
    heard = []
    bot.on_hand_made = heard.append

    bot.ingestion.emit_hand_made(HandResult("ok", 7))

    assert heard == [HandResult("ok", 7)]


async def test_a_stop_after_the_window_was_told_sends_no_second_word(make_bot, monkeypatch):
    """Итог заведения уже ушёл окну, а отклик после него сорвался — второй
    вести нет: вакансия стоит в New, и «не удалось завести» было бы неправдой."""
    bot = wire(await make_bot(), FakeIngestion())

    async def told_then_broke(kit, request):
        kit.pipeline.emit_hand_made(HandResult("ok", 7))
        raise RuntimeError("отклик сорвался")

    monkeypatch.setattr(pasted_mod.hand_made, "ingest_by_hand", told_then_broke)

    assert await bot.ui_ingest_pasted_text(TEXT) == "told"


async def test_a_paste_while_the_slot_is_busy_is_refused_without_calling_the_intake(
    make_bot, busy_slot, requests_seen
):
    """Занятое место отбивает приём, не начиная работы.

    Два прогона разом подрались бы за кэш отпечатков: первый пишет в него
    заведённое, второй сверяется с ним же.
    """
    bot = wire(await make_bot(), FakeIngestion())
    busy_slot(bot)

    assert await bot.ui_ingest_pasted_text(TEXT) == "busy"
    assert requests_seen == []


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



