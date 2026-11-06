"""Тумблеры, отметки чтения и выбор резюме живут в профиле.

Профиль 1 активен, профиль 2 — второй; активный меняется `make_active`.
Строки неактивного профиля читаются напрямую из таблиц «профиль × предмет»:
атрибуты общих моделей смотрят только в активный.
"""

from datetime import datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from backend.flows import channels as channel_flows
from backend.models import Aggregator, Blacklist, TelegramChannel, Vacancy
from backend.models.workspace import (
    Workspace,
    WorkspaceAggregator,
    WorkspaceBlacklist,
    WorkspaceChannel,
)
from backend.repository.aggregator_resumes import choose_resume, chosen_resume, drop_resume
from backend.repository.aggregators import create_aggregator, mark_run, set_aggregator_active
from backend.repository.blacklist import (
    create_blacklist,
    deactivate_blacklist_values,
    rename_blacklist_marks,
    set_blacklist_active,
    update_blacklist,
)
from backend.repository.channels import create_channel, reset_channel_cursor, set_channel_active
from backend.repository.vacancies_new import create_vacancy
from backend.repository.workspace_switches import copy_switches
from backend.repository.workspaces import make_active, owning_workspace_id
from backend.runtime_settings import RuntimeSettings
from tests.dbio import only_row, put, put_other_workspace
from tests.factories import (
    OTHER_WORKSPACE_ID,
    aggregator_switch_row,
    blacklist_row,
    blacklist_switch_row,
    channel_row,
    channel_switch_row,
    vacancy_row,
)
from tests.factories_aggregators import aggregator_resume_row, aggregator_row

async def _activate(session_factory, workspace_id: int) -> None:
    async with session_factory() as session, session.begin():
        assert await make_active(session, workspace_id)


async def _switch(session_factory, model, workspace_id: int, **where):
    """Строка «профиль × предмет» прямо из таблицы; пусто — строки нет."""
    async with session_factory() as session:
        return await session.scalar(
            select(model).filter_by(workspace_id=workspace_id, **where)
        )


def _new_vacancy_fields() -> dict:
    return {
        "title": "Python", "company_id": None, "hr_id": None, "source_url": None,
        "location": None, "remote": None, "grade": None, "salary_min": None,
        "salary_max": None, "salary_currency": None, "stack_required": [],
        "stack_preferred": [], "description": None, "notes": None, "posted_at": None,
    }


async def test_the_active_workspace_moves_down_and_up(session_factory):
    await put_other_workspace(session_factory)

    await _activate(session_factory, OTHER_WORKSPACE_ID)
    await _activate(session_factory, 1)

    async with session_factory() as session:
        rows = (await session.execute(select(Workspace.id, Workspace.is_active))).all()
        assert sorted(rows) == [(1, True), (OTHER_WORKSPACE_ID, False)]
        assert await make_active(session, 404) is False


async def test_read_marks_move_only_in_the_active_workspace(make_pipeline, session_factory):
    channel, site = channel_row(), aggregator_row()
    await put(session_factory, channel, site)
    await put_other_workspace(session_factory)
    before = datetime(2026, 1, 1, 12, 0)
    await put(
        session_factory,
        channel_switch_row(channel.id, last_processed_msg_id=10),
        channel_switch_row(channel.id, workspace_id=OTHER_WORKSPACE_ID, last_processed_msg_id=20),
        aggregator_switch_row(site.id, workspace_id=OTHER_WORKSPACE_ID, last_run_at=before),
    )

    await channel_flows.advance_cursor(await make_pipeline(), channel.id, 250)
    async with session_factory() as session, session.begin():
        await mark_run(session, site.id, datetime(2026, 2, 1, 12, 0))
    assert (await _switch(session_factory, WorkspaceChannel, 1)).last_processed_msg_id == 250
    async with session_factory() as session, session.begin():
        assert await reset_channel_cursor(session, channel.id)

    assert (await _switch(session_factory, WorkspaceChannel, 1)).last_processed_msg_id is None
    channel_there = await _switch(session_factory, WorkspaceChannel, OTHER_WORKSPACE_ID)
    site_there = await _switch(session_factory, WorkspaceAggregator, OTHER_WORKSPACE_ID)
    assert channel_there.last_processed_msg_id == 20
    assert site_there.last_run_at == before


async def test_a_new_blacklist_entry_is_off_in_another_workspace(session_factory):
    await put_other_workspace(session_factory)
    async with session_factory() as session, session.begin():
        row, _ = await create_blacklist(session, kind="company", value="Рога")
        assert row.active is True

    await _activate(session_factory, OTHER_WORKSPACE_ID)

    assert (await only_row(session_factory, Blacklist)).active is False


async def test_blacklist_toggles_touch_only_the_active_workspace(session_factory):
    first, second = blacklist_row("company", "Рога"), blacklist_row("company", "Копыта")
    await put(session_factory, first, second)
    await put_other_workspace(session_factory)
    await put(
        session_factory,
        blacklist_switch_row(first.id, active=True),
        blacklist_switch_row(second.id, active=True),
        blacklist_switch_row(first.id, workspace_id=OTHER_WORKSPACE_ID, active=True),
        blacklist_switch_row(second.id, workspace_id=OTHER_WORKSPACE_ID, active=True),
    )

    async with session_factory() as session, session.begin():
        assert await set_blacklist_active(session, first.id, False)
        assert await deactivate_blacklist_values(session, "company", ["Копыта"]) == 1

    for row in (first, second):
        assert (await _switch(session_factory, WorkspaceBlacklist, 1, blacklist_id=row.id)).active is False
        there = await _switch(
            session_factory, WorkspaceBlacklist, OTHER_WORKSPACE_ID, blacklist_id=row.id
        )
        assert there.active is True


async def test_switching_an_aggregator_touches_only_the_active_workspace(session_factory):
    site = aggregator_row(is_logged_in=True)
    await put(session_factory, site)
    await put_other_workspace(session_factory)
    await put(
        session_factory,
        aggregator_switch_row(site.id, workspace_id=OTHER_WORKSPACE_ID, is_active=False),
    )

    async with session_factory() as session, session.begin():
        assert await set_aggregator_active(session, site.id, True) == "ok"

    assert (await only_row(session_factory, Aggregator)).is_active is True
    there = await _switch(session_factory, WorkspaceAggregator, OTHER_WORKSPACE_ID)
    assert there.is_active is False


async def test_a_fresh_aggregator_reads_its_switch(session):
    row, outcome = await create_aggregator(session, "https://hh.ru", "HeadHunter", None)

    assert outcome == "created"
    assert row.is_active is False


async def test_a_channel_added_in_one_workspace_is_off_in_another(session_factory):
    await put_other_workspace(session_factory)
    async with session_factory() as session, session.begin():
        await create_channel(session, "pyjobs", "Питон", None)

    await _activate(session_factory, OTHER_WORKSPACE_ID)

    channel = await only_row(session_factory, TelegramChannel)
    assert channel.is_active is False
    assert channel.last_processed_msg_id is None


async def test_switching_a_channel_touches_only_the_active_workspace(session_factory):
    channel = channel_row()
    await put(session_factory, channel)
    await put_other_workspace(session_factory)
    await put(
        session_factory,
        channel_switch_row(channel.id, is_active=True),
        channel_switch_row(channel.id, workspace_id=OTHER_WORKSPACE_ID, is_active=True),
    )

    async with session_factory() as session, session.begin():
        assert await set_channel_active(session, channel.id, False) == "ok"

    assert (await only_row(session_factory, TelegramChannel)).is_active is False
    assert (await _switch(session_factory, WorkspaceChannel, OTHER_WORKSPACE_ID)).is_active is True


async def test_choosing_a_resume_is_per_workspace(session_factory):
    site = aggregator_row()
    await put(session_factory, site)
    resume = aggregator_resume_row(site.id)
    await put(session_factory, resume)
    await put_other_workspace(session_factory)

    async with session_factory() as session, session.begin():
        await choose_resume(session, site.id, resume.id)
        assert (await chosen_resume(session, site.id)).id == resume.id
    await _activate(session_factory, OTHER_WORKSPACE_ID)

    async with session_factory() as session:
        assert await chosen_resume(session, site.id) is None


async def test_a_dropped_resume_unchooses_itself(session_factory):
    site = aggregator_row()
    await put(session_factory, site)
    resume = aggregator_resume_row(site.id)
    await put(session_factory, resume)
    async with session_factory() as session, session.begin():
        await choose_resume(session, site.id, resume.id)

    async with session_factory() as session, session.begin():
        await drop_resume(session, site.id, resume.url)

    assert (await _switch(session_factory, WorkspaceAggregator, 1)).chosen_resume_id is None


async def test_renaming_a_mark_moves_it_in_every_workspace(session_factory):
    mark = blacklist_row("company", "Ромашка")
    await put(session_factory, mark)
    await put_other_workspace(session_factory)
    await put(
        session_factory, blacklist_switch_row(mark.id, workspace_id=OTHER_WORKSPACE_ID, active=True)
    )

    async with session_factory() as session, session.begin():
        await rename_blacklist_marks(
            session, "company", old_value="Ромашка", new_value="Ромашка Групп"
        )

    assert (await only_row(session_factory, Blacklist)).value == "Ромашка Групп"
    assert (await _switch(session_factory, WorkspaceBlacklist, OTHER_WORKSPACE_ID)).active is True


async def test_merging_marks_keeps_each_workspace_on(session_factory):
    moving, standing = blacklist_row("company", "Ромашка"), blacklist_row("company", "Лютик")
    await put(session_factory, moving, standing)
    await put_other_workspace(session_factory)
    await put(
        session_factory,
        blacklist_switch_row(moving.id, active=True),
        blacklist_switch_row(standing.id, workspace_id=OTHER_WORKSPACE_ID, active=True),
    )

    async with session_factory() as session, session.begin():
        await rename_blacklist_marks(session, "company", old_value="Ромашка", new_value="Лютик")

    for workspace_id in (1, OTHER_WORKSPACE_ID):
        assert (await _switch(
            session_factory, WorkspaceBlacklist, workspace_id, blacklist_id=standing.id
        )).active is True
        moved = await _switch(session_factory, WorkspaceBlacklist, workspace_id, blacklist_id=moving.id)
        assert moved is None or moved.active is False


async def test_a_newly_marked_source_goes_off_in_its_workspace(session_factory):
    channel, mark = channel_row(username="pyjobs"), blacklist_row("channel", "@other")
    await put(session_factory, channel, mark)
    await put_other_workspace(session_factory)
    await put(
        session_factory,
        channel_switch_row(channel.id, is_active=True),
        channel_switch_row(channel.id, workspace_id=OTHER_WORKSPACE_ID, is_active=True),
        blacklist_switch_row(mark.id, workspace_id=OTHER_WORKSPACE_ID, active=True),
    )

    async with session_factory() as session, session.begin():
        assert await update_blacklist(session, mark.id, value="@pyjobs")

    assert (await _switch(session_factory, WorkspaceChannel, OTHER_WORKSPACE_ID)).is_active is False
    assert (await _switch(session_factory, WorkspaceChannel, 1)).is_active is True


async def test_the_same_post_makes_two_vacancies_in_two_workspaces(session_factory):
    channel = channel_row()
    await put(session_factory, channel)
    await put_other_workspace(session_factory)

    await put(
        session_factory,
        vacancy_row(source_channel_id=channel.id, source_msg_id=7),
        vacancy_row(source_channel_id=channel.id, source_msg_id=7, workspace_id=OTHER_WORKSPACE_ID),
    )

    with pytest.raises(IntegrityError):
        await put(session_factory, vacancy_row(source_channel_id=channel.id, source_msg_id=7))


async def test_a_new_vacancy_lands_in_the_active_workspace(session_factory):
    await put_other_workspace(session_factory)
    await _activate(session_factory, OTHER_WORKSPACE_ID)

    async with session_factory() as session, session.begin():
        await create_vacancy(session, _new_vacancy_fields())

    assert (await only_row(session_factory, Vacancy)).workspace_id == OTHER_WORKSPACE_ID


async def test_the_cv_path_is_per_workspace(session_factory):
    await put_other_workspace(session_factory)
    settings = await RuntimeSettings.load(session_factory)
    await settings.set_cv_path("a.pdf")

    await _activate(session_factory, OTHER_WORKSPACE_ID)
    await settings.reload()

    assert settings.cv_path == ""


async def test_a_vacancy_knows_whether_it_is_in_the_active_workspace(session_factory):
    await put_other_workspace(session_factory)
    await put(
        session_factory,
        vacancy_row(title="своя"), vacancy_row(title="чужая", workspace_id=OTHER_WORKSPACE_ID),
    )

    async with session_factory() as session:
        rows = (await session.scalars(select(Vacancy).order_by(Vacancy.id))).all()
        assert [(v.title, v.in_active_workspace) for v in rows] == [("своя", True), ("чужая", False)]
        assert (await session.scalars(
            select(Vacancy.title).where(Vacancy.in_active_workspace)
        )).all() == ["своя"]


async def test_a_vacancy_is_owned_by_its_workspace(session_factory):
    await put_other_workspace(session_factory)
    vacancy = vacancy_row(workspace_id=OTHER_WORKSPACE_ID)
    await put(session_factory, vacancy)

    async with session_factory() as session:
        assert await owning_workspace_id(session, vacancy.id) == OTHER_WORKSPACE_ID
        assert await owning_workspace_id(session, None) == 1


async def test_copied_switches_carry_toggles_and_choice_but_not_read_marks(session_factory):
    channel, site, mark = channel_row(), aggregator_row(), blacklist_row("company", "Рога")
    await put(session_factory, channel, site, mark)
    resume = aggregator_resume_row(site.id)
    await put(session_factory, resume)
    await put_other_workspace(session_factory)
    await put(
        session_factory,
        channel_switch_row(channel.id, is_active=True, last_processed_msg_id=77),
        aggregator_switch_row(
            site.id, is_active=True, last_run_at=datetime(2026, 1, 1), chosen_resume_id=resume.id
        ),
        blacklist_switch_row(mark.id, active=True),
    )

    async with session_factory() as session, session.begin():
        await copy_switches(session, 1, OTHER_WORKSPACE_ID)

    copied_channel = await _switch(session_factory, WorkspaceChannel, OTHER_WORKSPACE_ID)
    assert (copied_channel.is_active, copied_channel.last_processed_msg_id) == (True, None)
    copied_site = await _switch(session_factory, WorkspaceAggregator, OTHER_WORKSPACE_ID)
    assert (copied_site.is_active, copied_site.last_run_at, copied_site.chosen_resume_id) == (
        True, None, resume.id
    )
    assert (await _switch(session_factory, WorkspaceBlacklist, OTHER_WORKSPACE_ID)).active is True
