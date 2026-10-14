"""Отклик в Telegram: письмо, доставка и след в базе."""

import time

from backend.applying.result import Missed, TelegramClosed
from backend.applying.telegram import via_telegram
from backend.models import Application, ApplicationVia, Message, VacancyEvent
from tests.backend.fixtures.applying import TG
from tests.dbio import all_rows, put
from tests.factories import days_ago, message_row



async def test_the_first_letter_goes_with_the_resume(telegram_case):
    kit, vacancy, sent = await telegram_case()
    assert await via_telegram(kit, vacancy.id, TG) == "applied"
    ((_, _, attachment),) = sent
    assert attachment is not None
    (row,) = await all_rows(kit.pipeline.session_factory, Application)
    assert row.via is ApplicationVia.TELEGRAM and row.target == "@hr_name"


async def test_without_a_file_the_letter_goes_with_the_resume_link(telegram_case):
    """Строку дописывает код после модели и её проверки: проверка, отбивающая
    слово «резюме», её не видит."""
    kit, vacancy, sent = await telegram_case(resume="https://hh.ru/resume/1")

    assert await via_telegram(kit, vacancy.id, TG) == "applied"

    ((_, text, attachment),) = sent
    assert attachment is None
    assert text.splitlines()[-1] == "Резюме: https://hh.ru/resume/1"


async def test_without_a_file_or_link_the_letter_is_not_sent(telegram_case):
    kit, vacancy, sent = await telegram_case(resume=False)

    outcome = await via_telegram(kit, vacancy.id, TG)

    assert outcome == Missed("письмо не готово: cv_missing") and sent == []


async def test_the_letter_model_reads_the_post_itself(telegram_case):
    """Язык письма и просьбы поста видны только в исходном тексте: разбор их теряет."""
    kit, vacancy, sent = await telegram_case()

    await via_telegram(kit, vacancy.id, TG)

    ((_, text, _),) = sent
    assert vacancy.raw_text in text


async def test_a_letter_with_the_file_gets_no_link_line(telegram_case):
    kit, vacancy, sent = await telegram_case()

    await via_telegram(kit, vacancy.id, TG)

    ((_, text, _),) = sent
    assert "Резюме:" not in text


async def test_a_second_vacancy_of_the_same_hr_gets_a_short_note(telegram_case):
    kit, vacancy, sent = await telegram_case(prior_letter=True)
    await via_telegram(kit, vacancy.id, TG)
    _, text, attachment = sent[-1]
    assert attachment is None and text.startswith("Ещё одна ваша вакансия")


async def test_a_rerun_writes_the_full_letter_again(telegram_case):
    """Прогон заново — отклик как новый: наше прежнее письмо по этой же вакансии
    не делает его припиской «ещё одна вакансия»."""
    kit, vacancy, sent = await telegram_case()
    await put(kit.pipeline.session_factory, message_row(
        hr_id=vacancy.hr_id, vacancy_id=vacancy.id, is_incoming=False, sent_at=days_ago(1)))
    await via_telegram(kit, vacancy.id, TG)
    ((_, _, attachment),) = sent
    assert attachment is not None


async def test_a_flood_wait_is_a_lesson_and_is_stored(telegram_case):
    kit, vacancy, _ = await telegram_case(flood_wait=300)
    outcome = await via_telegram(kit, vacancy.id, TG)
    assert isinstance(outcome.lesson, TelegramClosed)
    assert kit.pipeline.rs.flood_wait_until_ts > time.time()


async def test_a_sent_letter_is_an_application_even_if_recording_breaks(telegram_case, monkeypatch):
    """Письмо уже у HR: сорвавшаяся запись не повод пробовать следующий способ —
    работодатель получил бы второй отклик."""
    kit, vacancy, sent = await telegram_case()

    async def broken(session, entry):
        raise RuntimeError("база недоступна")

    monkeypatch.setattr("backend.applying.telegram.record_application", broken)
    assert await via_telegram(kit, vacancy.id, TG) == "applied" and len(sent) == 1


async def test_simulation_records_without_sending(telegram_case):
    kit, vacancy, sent = await telegram_case(simulated=True)
    assert await via_telegram(kit, vacancy.id, TG) == "applied"
    assert sent == [] and await all_rows(kit.pipeline.session_factory, Message) == []
    (event,) = [e for e in await all_rows(kit.pipeline.session_factory, VacancyEvent)
                if e.kind == "applied"]
    assert event.payload["simulated"] is True


async def test_the_letter_is_delivered_to_the_hr_account_and_kept_in_the_chat(telegram_case):
    """Номер учётной записи не меняется, ник меняется: письмо идёт по номеру, если он есть."""
    kit, vacancy, sent = await telegram_case(hr_user_id=777)
    await via_telegram(kit, vacancy.id, TG)
    ((target, _, _),) = sent
    (message,) = await all_rows(kit.pipeline.session_factory, Message)
    assert target == 777 and message.vacancy_id == vacancy.id and not message.is_incoming
