"""Стенд откликателя: набор агента и вакансии, на которые есть чем откликнуться."""

import pytest

from tests.dbio import put
from tests.factories import hr_row, vacancy_row
from tests.factories_aggregators import mail_account_row, vacancy_contact_row
from tests.fakes.agent import kit_for
from tests.fakes.browser import FakeBrowser


@pytest.fixture
async def kit(make_pipeline):
    """Набор откликателя на настоящем конвейере и браузере-подделке."""
    return kit_for(await make_pipeline(), browser=FakeBrowser())


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
