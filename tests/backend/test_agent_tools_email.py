"""Отклик письмом: только на адрес из контактов, только с резюме, второй раз не уходит."""

import smtplib

import pytest

from backend.agent.jobs import Applied, Failed
from backend.agent.tools_applier import applier_tools
from backend.models import Application, ContactAddedBy, VacancyEvent
from backend.repository.app_settings import CV_PATH_KEY
from backend.repository.mail_account import MailSettings, save_mail_account
from tests.dbio import all_rows, put
from tests.factories import vacancy_row
from tests.factories_aggregators import vacancy_contact_row
from tests.fakes.agent import apply_job, kit_for, tool


@pytest.fixture
def sent(monkeypatch):
    letters = []
    monkeypatch.setattr("adapters.smtp_mail.send_mail", lambda account, mail: letters.append(mail))
    return letters


@pytest.fixture
def ready(session_factory, session, tmp_path, make_pipeline):
    """Отклик письмом на вакансию с контактом; почту, резюме и симуляцию задаёт тест."""

    async def build(*, simulated=False, mail=True, resume=True):
        vacancy = vacancy_row()
        await put(session_factory, vacancy)
        await put(session_factory,
                  vacancy_contact_row(vacancy.id, "hr@site.test", added_by=ContactAddedBy.PARSE),
                  vacancy_contact_row(vacancy.id, "boss@site.test", added_by=ContactAddedBy.PARSE))
        if mail:
            async with session.begin():
                await save_mail_account(
                    session, MailSettings("me@mail.test", "secret", "smtp.mail.test", 465)
                )
        cv = tmp_path / "cv.pdf"
        if resume:
            cv.write_bytes(b"%PDF")
        job = apply_job(vacancy.id, method="email", target="hr@site.test", simulated=simulated)
        pipeline = await make_pipeline()
        await pipeline.rs.set_app(CV_PATH_KEY, str(cv))
        return job, tool(applier_tools(kit_for(pipeline), job), "send_email")

    return build


async def test_a_letter_to_a_vacancy_contact_goes_out_and_is_recorded(ready, sent, session_factory):
    job, send = await ready()

    await send(address="HR@site.test", subject="Отклик\nна вакансию", body="Текст")

    assert [(m.to, m.subject, m.body, m.attachment.name) for m in sent] == [
        ("HR@site.test", "Отклик на вакансию", "Текст", "cv.pdf")
    ]
    (row,) = await all_rows(session_factory, Application)
    assert (row.via.value, row.target, row.letter) == ("email", "HR@site.test", "Текст")
    assert job.outcome == Applied(row.id)


async def test_an_address_outside_the_contacts_is_refused(ready, sent):
    job, send = await ready()

    answer = await send(address="boss@other.test", subject="S", body="B")

    assert sent == [] and job.outcome is None and "контакт" in answer


async def test_without_mail_settings_the_way_fails(ready, sent):
    job, send = await ready(mail=False)

    answer = await send(address="hr@site.test", subject="S", body="B")

    assert sent == [] and "не настроена" in answer
    assert isinstance(job.outcome, Failed)


async def test_without_a_resume_file_the_way_fails(ready, sent):
    job, send = await ready(resume=False)

    await send(address="hr@site.test", subject="S", body="B")

    assert sent == [] and job.outcome == Failed("нет файла резюме")


async def test_a_second_letter_to_the_same_address_does_not_go(ready, sent):
    job, send = await ready()
    await send(address="hr@site.test", subject="S", body="B")

    answer = await send(address="hr@site.test", subject="S", body="B")

    assert len(sent) == 1 and "уже" in answer


async def test_a_simulated_letter_is_recorded_but_not_sent(ready, sent, session_factory):
    job, send = await ready(simulated=True)

    await send(address="hr@site.test", subject="S", body="B")

    assert sent == [] and len(await all_rows(session_factory, Application)) == 1
    (event,) = [e for e in await all_rows(session_factory, VacancyEvent) if e.kind == "applied_elsewhere"]
    assert event.payload["simulated"] is True


@pytest.mark.parametrize("trouble", [
    smtplib.SMTPRecipientsRefused({"hr@site.test": (550, b"no such user")}),
    ConnectionResetError("связь оборвалась"),
])
async def test_a_letter_the_server_refused_is_a_failure_not_an_application(
    ready, session_factory, monkeypatch, trouble
):
    def refuse(account, mail):
        raise trouble

    monkeypatch.setattr("adapters.smtp_mail.send_mail", refuse)
    job, send = await ready()

    await send(address="hr@site.test", subject="S", body="B")

    assert isinstance(job.outcome, Failed) and "не принял" in job.outcome.reason
    assert await all_rows(session_factory, Application) == []


async def test_after_a_recorded_application_no_second_letter_goes(ready, sent):
    """Второе письмо другому контакту того же работодателя — второй отклик."""
    job, send = await ready()
    await send(address="hr@site.test", subject="S", body="B")

    answer = await send(address="boss@site.test", subject="S", body="B")

    assert len(sent) == 1 and "уже записан" in answer


@pytest.mark.parametrize(("subject", "body"), [(" ", "Текст"), ("Отклик", " ")])
async def test_a_letter_without_a_subject_or_a_text_does_not_go_out(
    ready, sent, session_factory, subject, body
):
    job, send = await ready()

    answer = await send(address="hr@site.test", subject=subject, body=body)

    assert sent == [] and job.outcome is None
    assert await all_rows(session_factory, Application) == []
    assert "тем" in answer.lower()
