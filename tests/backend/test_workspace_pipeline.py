"""Конвейер работает только в активном профиле; чужой заморожен.

Активен профиль 1, данные лежат в профиле 2.
"""

import pytest

from backend.flows import embeddings
from backend.flows.handover import new_to_apply
from backend.models import TrashEvent, VacancyStatus
from backend.repository.hr_identify import count_recent_outgoing_with_vacancy_for_hr
from backend.repository.vacancies_ghosting import mark_ghosted_vacancies
from backend.repository.vacancies_life import (
    record_trash_event,
    source_seen,
    vacancies_at_address,
)
from backend.repository.workspaces import make_active
from tests.dbio import all_rows, put, put_other_workspace
from tests.factories import (
    OTHER_WORKSPACE_ID,
    TEST_WORKSPACE_ID,
    channel_row,
    days_ago,
    hr_row,
    message_row,
    trash_event_row,
    vacancy_row,
)
from tests.factories_aggregators import aggregator_row


async def test_a_post_seen_in_another_workspace_is_new_here(session, session_factory):
    site = aggregator_row()
    await put_other_workspace(session_factory)
    await put(session_factory, site)
    await put(
        session_factory,
        vacancy_row(source_aggregator_id=site.id, source_key="stored",
                    workspace_id=OTHER_WORKSPACE_ID),
        trash_event_row(source_aggregator_id=site.id, source_key="trashed",
                        workspace_id=OTHER_WORKSPACE_ID),
    )

    assert not await source_seen(session, site.id, "stored")
    assert not await source_seen(session, site.id, "trashed")


async def test_a_trash_mark_of_another_workspace_does_not_hide_this_one(session_factory):
    channel = channel_row()
    await put_other_workspace(session_factory)
    await put(session_factory, channel)
    await put(
        session_factory,
        trash_event_row(source_channel_id=channel.id, source_msg_id=7,
                        workspace_id=OTHER_WORKSPACE_ID),
    )

    async with session_factory() as session, session.begin():
        await record_trash_event(
            session, vacancy_row(source_channel_id=channel.id, source_msg_id=7), "реклама"
        )

    marks = await all_rows(session_factory, TrashEvent)
    assert sorted(m.workspace_id for m in marks) == [TEST_WORKSPACE_ID, OTHER_WORKSPACE_ID]


async def test_a_hand_made_repeat_is_found_only_here(session, session_factory):
    await put_other_workspace(session_factory)
    await put(
        session_factory,
        vacancy_row(source_url="https://hh.ru/vacancy/123", workspace_id=OTHER_WORKSPACE_ID),
    )

    assert await vacancies_at_address(session, "https://hh.ru/vacancy/123") == []


async def test_duplicates_are_searched_only_here(make_pipeline, session_factory):
    mine = vacancy_row(embedding=[0.1, 0.2])
    await put_other_workspace(session_factory)
    await put(
        session_factory, mine, vacancy_row(embedding=[0.3, 0.4], workspace_id=OTHER_WORKSPACE_ID)
    )
    pipeline = await make_pipeline()

    await embeddings.ensure_embedding_cache(pipeline, width=2)

    assert pipeline.embeddings.ids.tolist() == [mine.id]


@pytest.mark.usefixtures("one_vector")
async def test_orphans_are_picked_only_here(parsed, make_pipeline, session_factory):
    await put_other_workspace(session_factory)
    await put(
        session_factory,
        vacancy_row(title=None, is_parsed=False, raw_text="текст", workspace_id=OTHER_WORKSPACE_ID),
    )
    pipeline = await make_pipeline()

    assert await pipeline.recover_orphan_vacancies() == 0
    assert parsed == []


async def test_ghosting_waits_for_the_frozen_workspace(session, session_factory):
    silent = vacancy_row(
        status=VacancyStatus.APPLIED, created_at=days_ago(30), workspace_id=OTHER_WORKSPACE_ID
    )
    await put_other_workspace(session_factory)
    await put(session_factory, silent)

    assert await mark_ghosted_vacancies(session, timeout_days=14) == []

    await make_active(session, OTHER_WORKSPACE_ID)

    assert await mark_ghosted_vacancies(session, timeout_days=14) == [silent.id]


async def test_new_to_apply_is_only_here(session_factory):
    mine = vacancy_row()
    await put_other_workspace(session_factory)
    await put(
        session_factory, mine, vacancy_row(workspace_id=OTHER_WORKSPACE_ID)
    )

    assert await new_to_apply(session_factory) == [mine.id]


async def test_a_letter_from_another_workspace_does_not_shorten_this_one(
    session, session_factory
):
    hr = hr_row()
    await put_other_workspace(session_factory)
    await put(session_factory, hr)
    here = vacancy_row(hr_id=hr.id)
    also_here = vacancy_row(hr_id=hr.id)
    there = vacancy_row(hr_id=hr.id, workspace_id=OTHER_WORKSPACE_ID)
    await put(session_factory, here, also_here, there)
    await put(
        session_factory,
        message_row(hr_id=hr.id, vacancy_id=there.id, tg_message_id=1,
                    is_incoming=False, sent_at=days_ago(1)),
    )

    assert await count_recent_outgoing_with_vacancy_for_hr(
        session, hr.id, window_days=14, other_than=here.id
    ) == 0

    await put(
        session_factory,
        message_row(hr_id=hr.id, vacancy_id=also_here.id, tg_message_id=2,
                    is_incoming=False, sent_at=days_ago(1)),
    )

    assert await count_recent_outgoing_with_vacancy_for_hr(
        session, hr.id, window_days=14, other_than=here.id
    ) == 1
