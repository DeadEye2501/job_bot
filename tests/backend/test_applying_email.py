"""Отклик письмом: модель приложения пишет, сервер почты принимает, отклик записывается."""

import asyncio
import threading
import time

import pytest

from backend.applying.email import via_email
from backend.applying.result import Missed
from backend.models import Application, ApplicationVia, VacancyEvent
from tests.backend.fixtures.applying import MAIL
from tests.dbio import all_rows
from tests.waiting import wait_until



async def test_a_letter_goes_with_the_resume_and_is_recorded(mail_case):
    kit, vacancy, outbox = await mail_case()
    assert await via_email(kit, vacancy.id, MAIL) == "applied"
    (mail,) = outbox
    assert mail.to == "hr@company.test" and mail.attachment is not None
    assert mail.subject == "Отклик на вакансию"
    (row,) = await all_rows(kit.pipeline.session_factory, Application)
    assert row.via is ApplicationVia.EMAIL and row.letter == "Текст"


async def test_a_refused_letter_is_missed_and_not_recorded(mail_case):
    kit, vacancy, _ = await mail_case(server_refuses=True)
    outcome = await via_email(kit, vacancy.id, MAIL)
    assert isinstance(outcome, Missed)
    assert await all_rows(kit.pipeline.session_factory, Application) == []


async def test_simulation_records_without_sending(mail_case):
    kit, vacancy, outbox = await mail_case(simulated=True)
    assert await via_email(kit, vacancy.id, MAIL) == "applied" and outbox == []
    (event,) = [e for e in await all_rows(kit.pipeline.session_factory, VacancyEvent)
                if e.kind == "applied"]
    assert event.payload["simulated"] is True


async def test_without_mail_settings_the_way_is_missed(mail_case):
    kit, vacancy, outbox = await mail_case(mail=False)
    outcome = await via_email(kit, vacancy.id, MAIL)
    assert isinstance(outcome, Missed) and outbox == []


async def test_without_a_resume_file_or_link_the_way_is_missed(mail_case):
    kit, vacancy, outbox = await mail_case(resume=False)
    outcome = await via_email(kit, vacancy.id, MAIL)
    assert outcome == Missed("нет ни файла резюме, ни ссылки на него") and outbox == []


async def test_without_a_file_the_letter_goes_with_the_resume_link(mail_case):
    """Ссылку дописывает код после модели: модель адреса не набирает."""
    kit, vacancy, outbox = await mail_case(resume="https://hh.ru/resume/1")

    assert await via_email(kit, vacancy.id, MAIL) == "applied"

    (mail,) = outbox
    assert mail.attachment is None
    assert mail.body.splitlines()[-1] == "Резюме: https://hh.ru/resume/1"


async def test_a_letter_with_the_file_gets_no_link_line(mail_case):
    kit, vacancy, outbox = await mail_case()

    await via_email(kit, vacancy.id, MAIL)

    assert "Резюме:" not in outbox[0].body


async def test_a_stop_while_the_letter_is_on_its_way_does_not_cut_it_off(mail_case, monkeypatch):
    """Прогон остановили, пока сервер почты принимал письмо: письмо всё равно
    записывается — иначе следующий прогон отправил бы второе."""
    kit, vacancy, _ = await mail_case()
    sending = threading.Event()

    def slow_server(account, mail):
        sending.set()
        time.sleep(0.2)

    monkeypatch.setattr("adapters.smtp_mail.send_mail", slow_server)
    applying = asyncio.create_task(via_email(kit, vacancy.id, MAIL))
    await wait_until(sending.is_set)

    applying.cancel()
    with pytest.raises(asyncio.CancelledError):
        await applying
    await asyncio.sleep(0.4)

    assert len(await all_rows(kit.pipeline.session_factory, Application)) == 1


async def test_a_sent_letter_is_an_application_even_if_recording_breaks(mail_case, monkeypatch):
    """Письмо уже у работодателя: сорвавшаяся запись не повод пробовать следующий способ."""
    kit, vacancy, outbox = await mail_case()

    async def broken(kit, entry):
        raise RuntimeError("база недоступна")

    monkeypatch.setattr("backend.applying.email.record_and_announce", broken)
    assert await via_email(kit, vacancy.id, MAIL) == "applied" and len(outbox) == 1


async def test_the_letter_needs_no_agent(mail_case):
    kit, vacancy, _ = await mail_case()
    await via_email(kit, vacancy.id, MAIL)
    assert kit.run_session.plans == [] and kit.browser.calls == []
