"""Переписка с HR идёт во всех профилях; чёрный список — профиля вакансии письма.

Активен профиль 2; вакансия лежит в профиле 1, и HR писали по ней.
"""

import pytest

from backend.flows import dm_classify
from backend.models import HR, Message, Vacancy, VacancyStatus
from backend.payloads import Classification
from backend.repository.workspaces import make_active
from tests.dbio import all_rows, only_row, put, put_other_workspace, their_letters
from tests.factories import (
    OTHER_WORKSPACE_ID,
    TEST_WORKSPACE_ID,
    blacklist_row,
    blacklist_switch_row,
    hr_row,
    message_row,
    vacancy_row,
)
from tests.fakes.telegram import FakeTelegramClient
from tests.fakes.telegram_objects import incoming


@pytest.fixture
async def frozen(session_factory) -> tuple[HR, Vacancy]:
    """HR и вакансия замороженного профиля 1, по которой ему писали."""
    hr = hr_row(telegram_user_id=777, telegram_username="maria")
    vacancy = vacancy_row(status=VacancyStatus.APPLIED, workspace_id=TEST_WORKSPACE_ID)
    await put_other_workspace(session_factory)
    await put(session_factory, hr, vacancy)
    await put(
        session_factory,
        message_row(hr_id=hr.id, vacancy_id=vacancy.id, is_incoming=False, tg_message_id=1),
    )
    async with session_factory() as session, session.begin():
        await make_active(session, OTHER_WORKSPACE_ID)
    return hr, vacancy


@pytest.fixture
def asked(monkeypatch) -> list[str]:
    """Разбор ответа HR зовёт на созвон; отдаёт тексты, с которыми его спросили."""
    texts: list[str] = []

    async def classify_hr_reply(ask, client, model):
        texts.append(ask.text)
        return Classification(status=VacancyStatus.INVITATION, explanation="зовут"), None

    monkeypatch.setattr("backend.flows.dm_classify.classify_hr_reply", classify_hr_reply)
    return texts


async def _mark_hr_in(session_factory, workspace_id: int) -> None:
    """Отметить HR в чёрном списке только в этом профиле."""
    mark = blacklist_row("hr", "@maria")
    await put(session_factory, mark)
    await put(session_factory, blacklist_switch_row(mark.id, workspace_id=workspace_id, active=True))


async def _status(session_factory) -> VacancyStatus:
    return (await only_row(session_factory, Vacancy)).status


@pytest.mark.usefixtures("frozen")
async def test_a_reply_moves_a_vacancy_of_a_frozen_workspace(session_factory, deliver, asked):
    await deliver(incoming(text="давайте созвонимся"), client=FakeTelegramClient())

    assert asked == ["давайте созвонимся"]
    assert await _status(session_factory) is VacancyStatus.INVITATION


@pytest.mark.usefixtures("frozen")
async def test_an_hr_marked_in_the_vacancy_workspace_is_ignored(session_factory, deliver, asked):
    await _mark_hr_in(session_factory, TEST_WORKSPACE_ID)

    await deliver(incoming(text="давайте созвонимся"), client=FakeTelegramClient())

    assert await their_letters(session_factory) == []
    assert asked == []
    assert await _status(session_factory) is VacancyStatus.APPLIED


@pytest.mark.usefixtures("frozen")
async def test_an_hr_marked_only_in_the_active_workspace_is_heard(
    session_factory, deliver, asked
):
    await _mark_hr_in(session_factory, OTHER_WORKSPACE_ID)

    await deliver(incoming(text="давайте созвонимся"), client=FakeTelegramClient())

    assert [m.text for m in await their_letters(session_factory)] == ["давайте созвонимся"]
    assert await _status(session_factory) is VacancyStatus.INVITATION


async def test_a_letter_without_a_vacancy_is_judged_by_the_active_workspace(
    session_factory, deliver
):
    await put_other_workspace(session_factory)
    await put(session_factory, hr_row(telegram_user_id=777, telegram_username="maria"))
    async with session_factory() as session, session.begin():
        await make_active(session, OTHER_WORKSPACE_ID)
    await _mark_hr_in(session_factory, OTHER_WORKSPACE_ID)

    await deliver(incoming(), client=FakeTelegramClient())

    assert await all_rows(session_factory, Message) == []


async def _read_a_burst(frozen, session_factory, make_pipeline) -> list[int]:
    """Разобрать пачку из одного письма HR по вакансии профиля 1; кто ждёт после."""
    hr, vacancy = frozen
    letter = message_row(hr_id=hr.id, vacancy_id=vacancy.id, tg_message_id=2)
    await put(session_factory, letter)
    pipeline = await make_pipeline()
    pipeline.dm_debounce.remember(hr.id, {
        "vacancy_id": vacancy.id, "msg_id": letter.id, "tg_msg_id": 2,
        "text": "давайте созвонимся",
    })
    await dm_classify.classify_and_apply_for_hr(pipeline, hr.id)
    return pipeline.dm_debounce.waiting()


async def test_a_burst_of_a_marked_hr_is_dropped(frozen, session_factory, make_pipeline, asked):
    await _mark_hr_in(session_factory, TEST_WORKSPACE_ID)

    assert await _read_a_burst(frozen, session_factory, make_pipeline) == []
    assert asked == []
    assert await _status(session_factory) is VacancyStatus.APPLIED


async def test_a_burst_of_an_hr_marked_only_in_the_active_workspace_is_read(
    frozen, session_factory, make_pipeline, asked
):
    await _mark_hr_in(session_factory, OTHER_WORKSPACE_ID)

    assert await _read_a_burst(frozen, session_factory, make_pipeline) == []
    assert asked == ["давайте созвонимся"]
    assert await _status(session_factory) is VacancyStatus.INVITATION
