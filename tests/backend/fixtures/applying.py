"""Стенд откликателя: набор агента и вакансии, на которые есть чем откликнуться."""

import smtplib

import pytest
from pyrogram.errors import FloodWait

from backend.llm.agent_letter import Letter
from backend.models import VacancyStatus
from backend.repository.app_settings import CV_PATH_KEY
from tests.dbio import put
from tests.factories import days_ago, hr_row, message_row, vacancy_row
from tests.factories_aggregators import aggregator_row, mail_account_row, vacancy_contact_row
from tests.fakes.agent import kit_for, scripted, scripted_kit
from tests.fakes.browser import FakeBrowser


@pytest.fixture
async def kit(make_pipeline):
    """Набор откликателя на настоящем конвейере и браузере-подделке."""
    return kit_for(await make_pipeline(), browser=FakeBrowser())


PAGE = "https://site.test/vacancy/1"
FORM = "https://company.test/apply"


@pytest.fixture
def board(session_factory):
    """Залогиненный агрегатор и вакансия с него: кнопка агрегатора, затем форма из контактов."""

    async def make(**vacancy):
        site = aggregator_row(host="site.test", is_logged_in=True, is_active=True)
        await put(session_factory, site)
        row = vacancy_row(**{"status": VacancyStatus.NEW, "source_aggregator_id": site.id,
                             "source_key": "vacancy/1", "source_url": PAGE, **vacancy})
        await put(session_factory, row)
        await put(session_factory, vacancy_contact_row(row.id, FORM))
        return site, row

    return make


async def _pipeline(make_pipeline, *, simulated: bool, resume=None):
    """Конвейер стенда: симуляция отправки и, если дан, путь к резюме."""
    pipeline = await make_pipeline()
    await pipeline.rs.set_app("send_locked", "true" if simulated else "false")
    if resume is not None:
        await pipeline.rs.set_app(CV_PATH_KEY, str(resume))
    return pipeline


@pytest.fixture
def kit_with(make_pipeline):
    """Набор с водителем по сценарию; `send_locked` — симуляция отправки."""

    async def make(steps, *, send_locked=False):
        return scripted_kit(await _pipeline(make_pipeline, simulated=send_locked), steps)

    return make


@pytest.fixture
async def two_vacancies(session_factory):
    """Две вакансии в New: у каждой HR с ником и почта в контактах; почта настроена."""
    await put(session_factory, mail_account_row())
    rows = []
    for number in (1, 2):
        hr = hr_row(telegram_username="hr_name")
        await put(session_factory, hr)
        row = vacancy_row(hr_id=hr.id, title=f"Вакансия {number}")
        await put(session_factory, row)
        await put(session_factory, vacancy_contact_row(row.id, "hr@company.test"))
        rows.append(row)
    return rows


@pytest.fixture
def telegram_case(make_pipeline, session_factory, tmp_path, monkeypatch, outbox):
    """Вакансия в New с HR `hr_name`, анкета, резюме, письмо от модели готово.

    `prior_letter` — этому HR уже писали о другой его вакансии; `flood_wait` —
    Telegram просит подождать столько секунд; `simulated` — симуляция отправки;
    `hr_user_id` — HR известен ещё и номером учётной записи.
    """

    async def make(*, prior_letter=False, flood_wait=None, simulated=False, hr_user_id=None):
        resume = tmp_path / "Резюме.pdf"
        resume.write_bytes(b"%PDF")
        hr = hr_row(telegram_username="hr_name", telegram_user_id=hr_user_id)
        await put(session_factory, hr)
        vacancy = vacancy_row(hr_id=hr.id)
        await put(session_factory, vacancy)
        if prior_letter:
            other = vacancy_row(hr_id=hr.id, title="Прежняя")
            await put(session_factory, other)
            await put(session_factory, message_row(hr_id=hr.id, vacancy_id=other.id,
                                                   is_incoming=False, sent_at=days_ago(1)))
        if flood_wait is not None:
            outbox.error = FloodWait(value=flood_wait)
        pipeline = await _pipeline(make_pipeline, simulated=simulated, resume=resume)
        pipeline.profile_block = "Иван Петров, Python-разработчик"

        async def generate_cover_letter(block, parsed, client, model, *, channel_ref=None):
            return "Здравствуйте! Откликаюсь на вакансию.", None

        monkeypatch.setattr("backend.applying.telegram_letter.generate_cover_letter", generate_cover_letter)
        return kit_for(pipeline, browser=FakeBrowser()), vacancy, outbox.sent

    return make


@pytest.fixture
def mail_case(make_pipeline, session_factory, tmp_path, monkeypatch):
    """Вакансия с адресом HR, почта настроена, резюме есть, письмо от модели готово.

    `server_refuses` — сервер почты не принимает письмо; `simulated` — симуляция;
    `mail` и `resume` — настроена ли почта и лежит ли файл резюме.
    """

    async def make(*, server_refuses=False, simulated=False, mail=True, resume=True):
        cv = tmp_path / "cv.pdf"
        if resume:
            cv.write_bytes(b"%PDF")
        if mail:
            await put(session_factory, mail_account_row())
        vacancy = vacancy_row()
        await put(session_factory, vacancy)
        await put(session_factory, vacancy_contact_row(vacancy.id, "hr@company.test"))
        pipeline = await _pipeline(make_pipeline, simulated=simulated, resume=cv)
        outbox = []

        def send_mail(account, mail):
            if server_refuses:
                raise smtplib.SMTPException("отказ")
            outbox.append(mail)

        async def write_letter(ask, client, model):
            return Letter("Отклик\nна вакансию", "Текст"), []

        monkeypatch.setattr("adapters.smtp_mail.send_mail", send_mail)
        monkeypatch.setattr("backend.applying.email.write_letter", write_letter)
        kit = kit_for(pipeline, browser=FakeBrowser(), run_session=scripted([]))
        return kit, vacancy, outbox

    return make
