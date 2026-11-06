"""Домен «Профили»: перечень с именами, смена, создание и удаление."""

import pytest

from backend.bot.media import MEDIA_DIR
from backend.flows.embeddings import similar_vacancy_id
from backend.models import Workspace
from client.bridge.events import LIST_CHANGED
from client.bridge.refusals import BUSY_CYCLE, NO_WORKSPACE
from tests.dbio import active_workspace_ids, all_rows, put, put_other_workspace
from tests.factories import (
    OTHER_WORKSPACE_ID,
    TEST_WORKSPACE_ID,
    profile_row,
    vacancy_row,
    workspace_row,
)


@pytest.fixture
def photo_write_fails(monkeypatch):
    """Запись копии фото падает, как на полном диске."""

    def refuse(*_args):
        raise OSError("нет места на диске")

    monkeypatch.setattr("backend.flows.workspaces.store_profile_photo", refuse)


async def _photo_in_first_profile(session_factory) -> None:
    (MEDIA_DIR / "profile" / "1").mkdir(parents=True, exist_ok=True)
    (MEDIA_DIR / "profile" / "1" / "photo.jpg").write_bytes(b"jpeg")
    async with session_factory() as session:
        async with session.begin():
            (await session.get(Workspace, TEST_WORKSPACE_ID)).photo_path = "profile/1/photo.jpg"


async def _news(hub) -> list[str]:
    return [one["kind"] for one in (await hub.events.take(after=0, timeout=0.01))["events"]]


@pytest.fixture
async def real_bot(hub, make_bot):
    """Настоящий бот на подделках на месте бота окна: замок — его место прогона."""
    hub.bot = await make_bot()
    return hub.bot


async def test_list_names_profiles_by_title(api, ask, session_factory):
    await put(session_factory, profile_row())
    await put_other_workspace(session_factory)

    answer = (await ask(api.workspaces.list))["ok"]

    assert answer["items"] == [
        {"id": TEST_WORKSPACE_ID, "name": "Python-разработчик", "active": True},
        {"id": OTHER_WORKSPACE_ID, "name": "Без должности", "active": False},
    ]


async def test_switching_is_refused_while_the_slot_is_taken(
    api, ask, real_bot, busy_slot, session_factory
):
    await put_other_workspace(session_factory)
    busy_slot(real_bot)

    answer = await ask(api.workspaces.switch, OTHER_WORKSPACE_ID)

    assert answer == {"fail": "denied", "detail": BUSY_CYCLE}
    assert await active_workspace_ids(session_factory) == [TEST_WORKSPACE_ID]


async def test_switching_without_a_bot_goes_through(api, ask, hub, session_factory):
    await put(session_factory, workspace_row(id=OTHER_WORKSPACE_ID, cv_path="C:/второе.pdf"))

    answer = await ask(api.workspaces.switch, OTHER_WORKSPACE_ID)

    assert "ok" in answer
    assert await active_workspace_ids(session_factory) == [OTHER_WORKSPACE_ID]
    assert hub.rs.cv_path == "C:/второе.pdf"
    assert await _news(hub) == [LIST_CHANGED, "contacts_lists_changed"]


async def test_switching_to_an_unknown_profile_is_refused(api, ask, session_factory):
    answer = await ask(api.workspaces.switch, 99)

    assert answer == {"fail": "denied", "detail": NO_WORKSPACE}
    assert await active_workspace_ids(session_factory) == [TEST_WORKSPACE_ID]


async def test_a_failure_after_the_switch_still_shows_the_new_profile(
    api, ask, hub, session_factory, photo_write_fails
):
    """Профиль уже создан и активен, упала только копия фото: окно и настройки
    обязаны видеть новый профиль — иначе следующее фото затёрло бы чужое."""
    await _photo_in_first_profile(session_factory)
    await hub.rs.reload()

    answer = await ask(api.workspaces.create, "personal")

    assert answer["fail"] == "broken"
    assert await active_workspace_ids(session_factory) != [TEST_WORKSPACE_ID]
    assert hub.rs.photo_path == ""
    assert await _news(hub) == [LIST_CHANGED, "contacts_lists_changed"]


async def test_a_failure_after_the_switch_through_the_bot_forgets_the_old_profile(
    api, ask, real_bot, session_factory, photo_write_fails
):
    await _photo_in_first_profile(session_factory)
    await real_bot.rs.reload()
    mine = vacancy_row(embedding=[0.1, 0.2])
    await put(session_factory, mine)
    assert await similar_vacancy_id(real_bot.ingestion, [0.1, 0.2]) == mine.id

    answer = await ask(api.workspaces.create, "personal")

    assert answer["fail"] == "denied"
    assert real_bot.rs.photo_path == ""
    assert await similar_vacancy_id(real_bot.ingestion, [0.1, 0.2]) is None


async def test_removing_the_last_profile_is_refused(api, ask, session_factory):
    answer = await ask(api.workspaces.remove)

    assert answer == {"fail": "denied", "detail": "Это единственный профиль"}
    assert await active_workspace_ids(session_factory) == [TEST_WORKSPACE_ID]


async def test_an_unknown_way_is_refused(api, ask, session_factory):
    answer = await ask(api.workspaces.create, "всё")

    assert answer["fail"] == "fields"
    assert len(await all_rows(session_factory, Workspace)) == 1


async def test_switching_through_the_bot_forgets_vectors_of_the_old_profile(
    api, ask, real_bot, session_factory
):
    await put_other_workspace(session_factory)
    mine = vacancy_row(embedding=[0.1, 0.2])
    await put(session_factory, mine)
    assert await similar_vacancy_id(real_bot.ingestion, [0.1, 0.2]) == mine.id

    answer = await ask(api.workspaces.switch, OTHER_WORKSPACE_ID)

    assert "ok" in answer
    assert await active_workspace_ids(session_factory) == [OTHER_WORKSPACE_ID]
    assert await similar_vacancy_id(real_bot.ingestion, [0.1, 0.2]) is None
